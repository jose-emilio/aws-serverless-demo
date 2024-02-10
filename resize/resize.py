import boto3
import os
import sys
import uuid
from urllib.parse import unquote_plus
from PIL import Image
import json
import time

s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
sns_client = boto3.client('sns')
dynamodb = boto3.client('dynamodb')

sns_topic = os.environ['tema']
bucket_destino = os.environ['bucket']
tabla = os.environ['tabla']

TIEMPO_EXPIRACION = 3600

def resize_image(image_path, resized_path, size):
  with Image.open(image_path) as image:
      image.thumbnail(size)
      image.save(resized_path)

def handler(event, context):
  registrosSQS = event['Records']
  for mensajeSQS in registrosSQS:
    colaArn = mensajeSQS['eventSourceARN']
    print('ColaArn: '+colaArn)
    print('ColaWeb:' + os.environ['colaWeb'])
    print('ColaThumbnail:' + os.environ['colaThumbnail'])
    if colaArn.endswith(os.environ['colaWeb']):
      queue_url = sqs_client.get_queue_url(QueueName=os.environ['colaWeb'])['QueueUrl']
      prefijo = 'web/'
      tipo = 'Web'
      size = (1024,768)
    elif colaArn.endswith(os.environ['colaThumbnail']):
      queue_url = sqs_client.get_queue_url(QueueName=os.environ['colaThumbnail'])['QueueUrl']
      prefijo = 'thumbnail/'
      tipo = 'Thumbnail'
      size = (400,300)
    recepcion = mensajeSQS['receiptHandle']
    mensajeSNS = mensajeSQS['body']
    mensajeSNSJSON = json.loads(mensajeSNS)
    registrosS3 = mensajeSNSJSON['Message']
    registrosS3JSON = json.loads(registrosS3)
    print('RegistrosS3JSON: '+str(registrosS3JSON))
    for registroS3 in registrosS3JSON['Records']:
      bucket=registroS3['s3']['bucket']['name']
      imagen=unquote_plus(registroS3['s3']['object']['key'])
      imagentmp = imagen.replace('/', '')
      ruta_descarga = '/tmp/{}{}'.format(uuid.uuid4(), imagentmp)
      ruta_carga = '/tmp/resized-{}'.format(imagentmp)
      s3_client.download_file(bucket, imagen, ruta_descarga)
      resize_image(ruta_descarga, ruta_carga, size)
      s3_client.upload_file(ruta_carga, bucket_destino, prefijo+imagen)
      url_firmada = s3_client.generate_presigned_url('get_object',
                                                     Params={'Bucket':bucket_destino,'Key':prefijo+imagen},
                                                     ExpiresIn=TIEMPO_EXPIRACION)
      respuesta = dynamodb.put_item(TableName=tabla,Item={'signed_url':{'S':url_firmada},
                                                          'ttl':{'N':str(int(time.time()+TIEMPO_EXPIRACION))},
                                                          'tipo':{'S':tipo}
                                                         }
                                 )
      respuesta = sns_client.publish(TopicArn=sns_topic,Message=url_firmada,Subject='URL de descarga de del archivo '+imagen+' en formato '+tipo)
    sqs_client.delete_message(QueueUrl=queue_url,ReceiptHandle=recepcion)