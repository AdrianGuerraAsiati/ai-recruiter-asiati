"""Inspect only the failing stage of the first CV, without printing personal data."""
import csv
import sys
import boto3
import pymupdf
from botocore.exceptions import ClientError

source = sys.argv[1]
with open(source, newline='', encoding='utf-8-sig') as f:
    candidate = next(csv.DictReader(f))['candidate_id']
session = boto3.Session(profile_name='ai-recruiter-bedrock',region_name='us-east-2')
try:
    data = session.client('s3').get_object(Bucket='ai-recruiter-cv-890876258895-us-east-2',Key=f'documents/cv-{candidate}.pdf')['Body'].read()
    print('S3_OK',len(data),flush=True)
except Exception as e:
    print('S3_ERROR',type(e).__name__,str(e)[:500]);sys.exit(1)
try:
    with pymupdf.open(stream=data,filetype='pdf') as doc:
        page=doc[0]
        png=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).tobytes('png')
    print('PDF_RENDER_OK',len(png),flush=True)
except Exception as e:
    print('PDF_RENDER_ERROR',type(e).__name__,str(e)[:500]);sys.exit(1)
try:
    result=session.client('bedrock-runtime').converse(modelId='us.amazon.nova-pro-v1:0',messages=[{'role':'user','content':[{'text':'Is this a CV? Answer YES or NO.'},{'image':{'format':'png','source':{'bytes':png}}}]}],inferenceConfig={'maxTokens':10,'temperature':0})
    print('BEDROCK_OK',result.get('usage',{}))
except ClientError as e:
    error=e.response.get('Error',{})
    print('BEDROCK_ERROR',error.get('Code'),str(error.get('Message',''))[:800]);sys.exit(1)
except Exception as e:
    print('BEDROCK_EXCEPTION',type(e).__name__,str(e)[:800]);sys.exit(1)
