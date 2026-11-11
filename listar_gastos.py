from boto3.dynamodb.conditions import Key
from comun import dynamodb, NO_AUTORIZADO, respuesta, autenticar, parametros_lista

def lambda_handler(event, context):
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
