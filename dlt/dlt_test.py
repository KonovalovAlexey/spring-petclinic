#!/usr/bin/env python
import boto3
import datetime
import hmac
import hashlib
import json
import requests
from urllib.parse import urlparse
import os
import traceback
from time import time, sleep

# Report Portal versions >= 5.0.0:
from reportportal_client import ReportPortalService


def timestamp():
    return str(int(time() * 1000))


def my_error_handler(exc_info):
    """
    This callback function will be called by async service client when error occurs.
    Return True if error is not critical and you want to continue work.
    :param exc_info: result of sys.exc_info() -> (type, value, traceback)
    :return:
    """
    print("Error occurred: {}".format(exc_info[1]))
    traceback.print_exception(*exc_info)


def report_portal(endpoint,
                  project,
                  token,
                  launch_name,
                  launch_doc,
                  dlt_alias,
                  test_id,
                  expected_success_rate,
                  success_rate,
                  p95_0,
                  errors,
                  success_p95_0,
                  status):
    service = ReportPortalService(endpoint=endpoint, project=project,
                                  token=token)

    # Start launch.
    service.start_launch(name=launch_name,
                         start_time=timestamp(),
                         description=launch_doc)

    # Start test item Report Portal versions >= 5.0.0:
    test = service.start_test_item(name="DLT Test",
                                   description=f"JAVA DLT Test: [WEB UI](https://{dlt_alias}/details/{test_id})",
                                   start_time=timestamp(),
                                   item_type="STEP",
                                   parameters={"Expected Success Rate": expected_success_rate,
                                               "Success Rate": success_rate,
                                               "P95 RESULT": p95_0,
                                               "SUCCESS_P95": success_p95_0
                                               })

    # Finish test item Report Portal versions >= 5.0.0.
    service.finish_test_item(item_id=test, end_time=timestamp(), status=status)

    # Finish launch.
    service.finish_launch(end_time=timestamp())

    # Failure to call terminate() may result in lost data.
    service.terminate()


def aws_sign_4_request(method='POST',
                       host=None,
                       rel_path_to_endpoint=None,
                       secret_key=None,
                       access_key=None,
                       security_token=None,
                       region=None,
                       payload=None,
                       ):
    service = 'execute-api'
    if method == 'POST':
        request_parameters = json.dumps(payload)
    else:
        request_parameters = ''

    # Key derivation functions. See:
    # https://docs.aws.amazon.com/general/latest/gr/signature-v4-examples.html#signature-v4-examples-python
    def sign(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def get_signature_key(key, _date_stamp, region_name, service_name):
        k_date = sign(('AWS4' + key).encode('utf-8'), _date_stamp)
        k_region = sign(k_date, region_name)
        k_service = sign(k_region, service_name)
        k_signing = sign(k_service, 'aws4_request')
        return k_signing

    # Create a date for headers and the credential string
    # noinspection DuplicatedCode
    t = datetime.datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')  # Date w/o time, used in credential scope

    # ************* CREATE A CANONICAL REQUEST *************
    # https://docs.aws.amazon.com/general/latest/gr/sigv4-create-canonical-request.html

    canonical_uri = rel_path_to_endpoint  # '/prod/scenarios'

    canonical_querystring = ''

    canonical_headers = 'host:' + host + '\n' + 'x-amz-date:' + amz_date + '\n' + \
                        'x-amz-security-token:' + security_token + '\n'

    signed_headers = 'host;x-amz-date;x-amz-security-token'

    payload_hash = hashlib.sha256(request_parameters.encode('utf-8')).hexdigest()

    canonical_request = method + '\n' + canonical_uri + '\n' + canonical_querystring + '\n' + canonical_headers + \
                        '\n' + signed_headers + '\n' + payload_hash

    # ************* TASK 2: CREATE THE STRING TO SIGN*************
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = date_stamp + '/' + region + '/' + service + '/' + 'aws4_request'
    string_to_sign = algorithm + '\n' + amz_date + '\n' + credential_scope + '\n' + hashlib.sha256(
        canonical_request.encode('utf-8')).hexdigest()

    signing_key = get_signature_key(secret_key, date_stamp, region, service)

    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # ************* TASK 4: ADD SIGNING INFORMATION TO THE REQUEST *************
    authorization_header = algorithm + ' ' + 'Credential=' + access_key + '/' + credential_scope + ', ' + \
                           'SignedHeaders=' + signed_headers + ', ' + 'Signature=' + signature

    headers = {
        'Authorization': authorization_header,
        'X-Amz-Date': amz_date,
        'X-Amz-Security-Token': security_token,
    }

    endpoint_url = 'https://' + host + rel_path_to_endpoint

    # ************* SEND THE REQUEST *************

    if method == 'POST':
        response = requests.post(endpoint_url, data=request_parameters, headers=headers)
    else:
        response = requests.get(endpoint_url, headers=headers, data='')

    response_json = response.json()

    return response_json


def main():
    host = urlparse(os.environ.get('DLT_API_HOST')).hostname
    dlt_alias = os.environ.get('DLT_ALIAS')
    region = os.environ.get('AWS_REGION')
    username = os.environ.get('COGNITO_USER')
    password = os.environ.get('COGNITO_PASSWORD')
    user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
    client_id = os.environ.get('COGNITO_CLIENT_ID')
    identity_pool_id = os.environ.get('COGNITO_IDENTITY_POOL_ID')
    client = boto3.client('cognito-idp')
    # Report Portal
    endpoint = os.environ.get('RP_ENDPOINT')
    project = os.environ.get('RP_PROJECT')
    # You can get UUID from user profile page in the Report Portal.
    token = os.environ.get('RP_TOKEN')
    launch_name = os.environ.get('RP_LAUNCH_NAME')
    launch_doc = os.environ.get('RP_LAUNCH_DOC')

    response = client.initiate_auth(
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': username,
            'PASSWORD': password
        },
        ClientId=client_id,
    )
    id_token = response['AuthenticationResult']['IdToken']

    cognito_identity_client = boto3.client('cognito-identity')
    # result = cognito_identity_client.list_identity_pools(
    #     MaxResults=1,
    # )
    # identity_pool_id = result['IdentityPools'][0]['IdentityPoolId']

    id_p = f'cognito-idp.{region}.amazonaws.com/{user_pool_id}'

    result = cognito_identity_client.get_id(
        IdentityPoolId=identity_pool_id,
        Logins={
            id_p: id_token
        }
    )

    identity_id = result['IdentityId']

    result = cognito_identity_client.get_credentials_for_identity(
        IdentityId=identity_id,
        Logins={
            id_p: id_token
        },
    )

    access_key_id = result['Credentials']['AccessKeyId']
    secret_key = result['Credentials']['SecretKey']
    session_token = result['Credentials']['SessionToken']

    with open('dlt_test.json', 'r') as file:
        payload = json.load(file)

    payload['testScenario']['scenarios']['Test']['requests'][0]['url'] = os.environ.get('APP_TARGET_URL')

    response = aws_sign_4_request(method='POST',
                                  host=host,
                                  rel_path_to_endpoint='/prod/scenarios',
                                  secret_key=secret_key,
                                  access_key=access_key_id,
                                  security_token=session_token,
                                  region=region,
                                  payload=payload,
                                  )

    test_id = response['testId']

    if response['status'] == 'running':
        print(f'Successfully running test {test_id}')

    print('\n' + f'Please refer to DLT WEB UI https://{dlt_alias}')

    while True:
        print('\n' + 'Waiting for test complete...........', flush=True)

        sleep(20)

        response = aws_sign_4_request(method='GET',
                                      host=host,
                                      rel_path_to_endpoint=f'/prod/scenarios/{test_id}',
                                      secret_key=secret_key,
                                      access_key=access_key_id,
                                      security_token=session_token,
                                      region=region,
                                      payload='',
                                      )

        print(f'Test {test_id} has status > {response["status"]}', flush=True)

        if response['status'] != 'running':
            break

    if response['status'] == 'complete':

        p95_0 = response['results']['p95_0']
        success_p95_0 = os.environ.get('SUCCESS_P95')
        expected_success_rate = os.environ.get('EXPECT_SUCCESS_RATE')
        errors = response['results']['fail']
        total = response['results']['throughput']

        if total > 0:
            success_rate = int(100 - errors * 100 / total)
            if float(p95_0) <= float(success_p95_0):
                print(
                    f'Test {test_id} passed successfully due to response time 95th percentile ({p95_0} < {success_p95_0})')

                if int(expected_success_rate) <= success_rate:
                    status = "PASSED"
                    print(f'Test {test_id} passed successfully due to request count success rate '
                          f'({expected_success_rate} < {success_rate})')
                    report_portal(endpoint=endpoint, project=project, token=token, launch_name=launch_name,
                                  launch_doc=launch_doc,
                                  dlt_alias=dlt_alias, test_id=test_id, expected_success_rate=expected_success_rate,
                                  success_rate=success_rate, p95_0=p95_0, errors=errors, success_p95_0=success_p95_0,
                                  status=status)

                else:
                    status = "FAILED"
                    print(f'Test {test_id} failing build due to request count success rate '
                          f'(Success rate {success_rate} less then expected {expected_success_rate}')
                    report_portal(endpoint=endpoint, project=project, token=token, launch_name=launch_name,
                                  launch_doc=launch_doc,
                                  dlt_alias=dlt_alias, test_id=test_id, expected_success_rate=expected_success_rate,
                                  success_rate=success_rate, p95_0=p95_0, errors=errors, success_p95_0=success_p95_0,
                                  status=status)
                    exit(1)
            else:
                status = "FAILED"
                print(f'Test {test_id} failing build due to response time 95th percentile ({p95_0} > {success_p95_0})')
                report_portal(endpoint=endpoint, project=project, token=token, launch_name=launch_name,
                              launch_doc=launch_doc,
                              dlt_alias=dlt_alias, test_id=test_id, expected_success_rate=expected_success_rate,
                              success_rate=success_rate, p95_0=p95_0, errors=errors, success_p95_0=success_p95_0,
                              status=status)
                exit(1)

    else:
        print(f'Test {test_id} failing build due to status {response["status"]}')
        exit(1)

    print(
        '\n' + f'For more information about the test, please, refer to the DLT WEB UI https://{dlt_alias}/details/{test_id}')


main()
