import json
from decimal import Decimal
from comun import dynamodb

tabla = dynamodb.Table('t_presupuestos')

def lambda_handler(event, context):
    # Entrada: mensajes de SQS; el cuerpo es el sobre de SNS y 'Message' es nuestro JSON.
    # parse_float=Decimal porque DynamoDB no acepta float.
    for registro in event['Records']:
        sobre = json.loads(registro['body'])
        msg = json.loads(sobre['Message'], parse_float=Decimal)
        tipo = msg.get('tipo_evento')
        print('Evento recibido:', tipo, msg.get('tenant_id'), msg.get('proyecto_id'))
        # Proceso
        if tipo == 'AsignacionCreada':
            # El evento trae el costo de la asignacion (horas x costo_hora del recurso)
            try:
                tabla.update_item(
                    Key={'tenant_id': msg['tenant_id'], 'proyecto_id': msg['proyecto_id']},
                    UpdateExpression='ADD costo_proyectado :c',
                    ConditionExpression='attribute_exists(tenant_id)',
                    ExpressionAttributeValues={':c': Decimal(str(msg['costo']))}
                )
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                print('El proyecto no tiene presupuesto, evento ignorado:', msg['proyecto_id'])
        else:
            print('Tipo de evento ignorado:', tipo)
    # Salida
    return {'statusCode': 200}
