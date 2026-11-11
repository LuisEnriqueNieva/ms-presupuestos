import os
from comun import (dynamodb, NO_AUTORIZADO, respuesta, autenticar, numero_positivo,
                   verificar_exceso)

def lambda_handler(event, context):
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
