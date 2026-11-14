# Lambda Presupuestos (ms-presupuestos). Una sola Lambda atiende varios endpoints.
# API Gateway (integration: lambda) manda en "requestPath" la ruta del recurso.
import os
from comun import dynamodb, NO_AUTORIZADO, respuesta, autenticar, proyecto_existe, numero_positivo, verificar_exceso
from datetime import datetime


def crear_presupuesto(event, context):
    # Proteger el Lambda
    sesion = autenticar(event)
    if not sesion:
        return NO_AUTORIZADO
    tenant_id = sesion['tenant_id']
    # Entrada (json)
    body = event.get('body') or {}
    proyecto_id = body.get('proyecto_id')
    monto_total = numero_positivo(body.get('monto_total'))
    if not proyecto_id or monto_total is None:
        return respuesta(400, mensaje='Falta proyecto_id o monto_total (numero mayor a 0)')
    # Proceso: el proyecto vive en otro microservicio
    if not proyecto_existe(event, proyecto_id):
        return respuesta(404, mensaje='El proyecto no existe')
    presupuesto = {
        'tenant_id': tenant_id,
        'proyecto_id': proyecto_id,
        'monto_total': monto_total,
        'gasto_acumulado': 0,
        'costo_proyectado': 0,
        'estado_presupuesto': 'NORMAL',
        'creado_en': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        dynamodb.Table('t_presupuestos').put_item(
            Item=presupuesto, ConditionExpression='attribute_not_exists(tenant_id)')
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return respuesta(409, mensaje='El proyecto ya tiene presupuesto')
    # Salida (json)
    return respuesta(200, presupuesto=presupuesto)


def buscar_presupuesto(event, context):
    # Proteger el Lambda
    sesion = autenticar(event)
    if not sesion:
        return NO_AUTORIZADO
    tenant_id = sesion['tenant_id']
    # Entrada (json)
    proyecto_id = (event.get('body') or {}).get('proyecto_id')
    if not proyecto_id:
        return respuesta(400, mensaje='Falta proyecto_id')
    # Proceso
    r = dynamodb.Table('t_presupuestos').get_item(
        Key={'tenant_id': tenant_id, 'proyecto_id': proyecto_id})
    # Salida (json)
    if 'Item' not in r:
        return respuesta(404, mensaje='El proyecto no tiene presupuesto')
    return respuesta(200, presupuesto=r['Item'])


def modificar_presupuesto(event, context):
    # Proteger el Lambda
    sesion = autenticar(event)
    if not sesion:
        return NO_AUTORIZADO
    tenant_id = sesion['tenant_id']
    # Entrada (json): solo se puede cambiar el monto_total
    body = event.get('body') or {}
    proyecto_id = body.get('proyecto_id')
    monto_total = numero_positivo(body.get('monto_total'))
    if not proyecto_id or monto_total is None:
        return respuesta(400, mensaje='Falta proyecto_id o monto_total (numero mayor a 0)')
    # Proceso
    try:
        r = dynamodb.Table('t_presupuestos').update_item(
            Key={'tenant_id': tenant_id, 'proyecto_id': proyecto_id},
            UpdateExpression='SET monto_total = :m',
            ConditionExpression='attribute_exists(tenant_id)',
            ExpressionAttributeValues={':m': monto_total},
            ReturnValues='ALL_NEW'
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return respuesta(404, mensaje='El proyecto no tiene presupuesto')
    presupuesto = r['Attributes']
    # Si el nuevo monto queda por debajo de lo gastado, ahora esta excedido
    if verificar_exceso(tenant_id, proyecto_id, presupuesto['gasto_acumulado'],
                        presupuesto['monto_total'], os.environ['TOPIC_PRESUPUESTOS_ARN']):
        presupuesto['estado_presupuesto'] = 'EXCEDIDO'
    # Salida (json)
    return respuesta(200, presupuesto=presupuesto)


RUTAS = {
    '/presupuestos/crear': crear_presupuesto,
    '/presupuestos/buscar': buscar_presupuesto,
    '/presupuestos/modificar': modificar_presupuesto,
}

def lambda_handler(event, context):
    ruta = (event or {}).get('requestPath')
    funcion = RUTAS.get(ruta)
    if funcion is None:
        return {'statusCode': 404, 'mensaje': 'Ruta no encontrada: %s' % ruta}
    return funcion(event, context)
