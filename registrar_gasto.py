import os
import uuid
from datetime import datetime
from comun import (dynamodb, NO_AUTORIZADO, respuesta, autenticar, numero_positivo,
                   verificar_exceso)

def lambda_handler(event, context):
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
