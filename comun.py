import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
_lambda = boto3.client('lambda')
_sns = boto3.client('sns')

NO_AUTORIZADO = {'statusCode': 403, 'mensaje': 'Forbidden - Acceso No Autorizado'}


def limpiar(obj):
    """DynamoDB devuelve Decimal; el JSON de salida necesita int/float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: limpiar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpiar(v) for v in obj]
    return obj


def a_decimal(obj):
    """DynamoDB no acepta float; los numeros del body se convierten a Decimal."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: a_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [a_decimal(v) for v in obj]
    return obj


def numero_positivo(valor):
    """Convierte a Decimal si es un numero > 0; si no, devuelve None."""
    try:
        n = Decimal(str(valor))
    except Exception:
        return None
    return n if n > 0 else None


def respuesta(codigo, **campos):
    return {'statusCode': codigo, **limpiar(campos)}


def _token(event):
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    return headers.get('authorization')


def autenticar(event):
    """Valida el token con ValidarTokenAcceso.
    Devuelve {'tenant_id', 'usuario_id', 'rol', ...} o None si no es valido."""
    token = _token(event)
    if not token:
        return None
    r = _lambda.invoke(FunctionName='ValidarTokenAcceso',
                       InvocationType='RequestResponse',
                       Payload=json.dumps({'token': token}))
    datos = json.loads(r['Payload'].read())
    if datos.get('statusCode') != 200:
        return None
    return datos


def proyecto_existe(event, proyecto_id):
    """Pregunta a ms-proyectos (Lambda BuscarProyecto) si el proyecto existe."""
    payload = {'headers': {'Authorization': _token(event)},
               'body': {'proyecto_id': proyecto_id}}
    r = _lambda.invoke(FunctionName='BuscarProyecto',
                       InvocationType='RequestResponse',
                       Payload=json.dumps(payload))
    datos = json.loads(r['Payload'].read())
    return datos.get('statusCode') == 200


def parametros_lista(body):
    """Limit y ExclusiveStartKey para paginar un Query."""
    try:
        limit = max(1, min(int(body.get('limit', 20)), 100))
    except (TypeError, ValueError):
        limit = 20
    kwargs = {'Limit': limit}
    if body.get('last_key'):
        kwargs['ExclusiveStartKey'] = body['last_key']
    return kwargs


def publicar(topic_arn, tipo_evento, tenant_id, datos):
    """Publica un evento en SNS. Si falla, no tumba la operacion principal."""
    mensaje = {'tipo_evento': tipo_evento, 'tenant_id': tenant_id, **datos}
    try:
        _sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(limpiar(mensaje)),
            MessageAttributes={
                'tipo_evento': {'DataType': 'String', 'StringValue': tipo_evento},
                'tenant_id': {'DataType': 'String', 'StringValue': tenant_id}
            }
        )
    except Exception as e:
        print('Error publicando evento:', str(e))


def verificar_exceso(tenant_id, proyecto_id, gasto_acumulado, monto_total, topic_arn):
    """Si el gasto supera el monto, marca EXCEDIDO y publica PresupuestoExcedido UNA sola vez.
    La condicion del update es atomica: solo el primero que cruza el limite lo logra."""
    if gasto_acumulado <= monto_total:
        return False
    try:
        dynamodb.Table('t_presupuestos').update_item(
            Key={'tenant_id': tenant_id, 'proyecto_id': proyecto_id},
            UpdateExpression='SET estado_presupuesto = :e',
            ConditionExpression='estado_presupuesto <> :e',
            ExpressionAttributeValues={':e': 'EXCEDIDO'}
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False  # ya estaba excedido, el evento ya se publico
    publicar(topic_arn, 'PresupuestoExcedido', tenant_id,
             {'proyecto_id': proyecto_id, 'monto_total': monto_total,
              'gasto_acumulado': gasto_acumulado})
    return True
