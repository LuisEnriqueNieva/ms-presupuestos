from datetime import datetime
from comun import (dynamodb, NO_AUTORIZADO, respuesta, autenticar, proyecto_existe,
                   numero_positivo)

def lambda_handler(event, context):
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
