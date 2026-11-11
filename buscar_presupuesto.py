from comun import dynamodb, NO_AUTORIZADO, respuesta, autenticar

def lambda_handler(event, context):
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
