# Lambda Gastos (ms-presupuestos). Una sola Lambda atiende varios endpoints.
# API Gateway (integration: lambda) manda en "requestPath" la ruta del recurso.
import os
import uuid
from boto3.dynamodb.conditions import Key
from comun import dynamodb, NO_AUTORIZADO, respuesta, autenticar, numero_positivo, verificar_exceso, parametros_lista
from datetime import datetime


def registrar_gasto(event, context):
    # Proteger el Lambda
    sesion = autenticar(event)
    if not sesion:
        return NO_AUTORIZADO
    tenant_id = sesion['tenant_id']
    # Entrada (json)
    body = event.get('body') or {}
    proyecto_id = body.get('proyecto_id')
    monto = numero_positivo(body.get('monto'))
    if not proyecto_id or monto is None:
        return respuesta(400, mensaje='Falta proyecto_id o monto (numero mayor a 0)')
    # Proceso 1: suma atomica al gasto acumulado (ADD no pierde gastos simultaneos)
    try:
        r = dynamodb.Table('t_presupuestos').update_item(
            Key={'tenant_id': tenant_id, 'proyecto_id': proyecto_id},
            UpdateExpression='ADD gasto_acumulado :m',
            ConditionExpression='attribute_exists(tenant_id)',
            ExpressionAttributeValues={':m': monto},
            ReturnValues='ALL_NEW'
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return respuesta(404, mensaje='El proyecto no tiene presupuesto')
    presupuesto = r['Attributes']
    # Proceso 2: se guarda el gasto en el historial
    gasto = {
        'tenant_id': tenant_id,
        'gasto_id': f'GAS-{tenant_id}-{uuid.uuid4().hex[:8]}',
        'proyecto_id': proyecto_id,
        'monto': monto,
        'concepto': body.get('concepto', ''),
        'fecha': body.get('fecha') or datetime.now().strftime('%Y-%m-%d'),
        'registrado_por': sesion['usuario_id']
    }
    dynamodb.Table('t_gastos').put_item(Item=gasto)
    # Proceso 3: si cruzo el limite, evento PresupuestoExcedido (una sola vez)
    excedido = verificar_exceso(tenant_id, proyecto_id, presupuesto['gasto_acumulado'],
                                presupuesto['monto_total'], os.environ['TOPIC_PRESUPUESTOS_ARN'])
    if excedido:
        presupuesto['estado_presupuesto'] = 'EXCEDIDO'
    # Salida (json)
    return respuesta(200, gasto=gasto, presupuesto=presupuesto)


def listar_gastos(event, context):
    # Proteger el Lambda
    sesion = autenticar(event)
    if not sesion:
        return NO_AUTORIZADO
    tenant_id = sesion['tenant_id']
    # Entrada (json): proyecto_id, limit y last_key son opcionales
    body = event.get('body') or {}
    # Proceso
    kwargs = parametros_lista(body)
    if body.get('proyecto_id'):
        kwargs['IndexName'] = 'gsi_proyecto'
        kwargs['KeyConditionExpression'] = Key('tenant_id').eq(tenant_id) & Key('proyecto_id').eq(body['proyecto_id'])
    else:
        kwargs['KeyConditionExpression'] = Key('tenant_id').eq(tenant_id)
    r = dynamodb.Table('t_gastos').query(**kwargs)
    # Salida (json)
    return respuesta(200, items=r['Items'], count=r['Count'],
                     last_key=r.get('LastEvaluatedKey'))


RUTAS = {
    '/gastos/registrar': registrar_gasto,
    '/gastos/listar': listar_gastos,
}

def lambda_handler(event, context):
    ruta = (event or {}).get('requestPath')
    funcion = RUTAS.get(ruta)
    if funcion is None:
        return {'statusCode': 404, 'mensaje': 'Ruta no encontrada: %s' % ruta}
    return funcion(event, context)
