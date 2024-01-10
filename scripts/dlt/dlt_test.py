import json
import os
import traceback
from time import sleep

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials
# Import additional modules required for Report Portal integration
from reportportal_client import RPClient
from reportportal_client.helpers import timestamp


def my_error_handler(exc_info):
    print("Error occurred: {}".format(exc_info[1]))
    traceback.print_exception(*exc_info)


def aws_sign_4_request(method, url, creds, region, payload=None, headers=None):
    request = AWSRequest(method=method, url=url, data=json.dumps(payload) if payload else None, headers=headers)
    SigV4Auth(creds, "execute-api", region).add_auth(request)
    response = requests.request(method=method, url=url, headers=dict(request.headers), data=request.data)
    response.raise_for_status()
    return response.json()


def create_test_scenario_payload(test_type, target_url, region, test_id, test_name, task_count, concurrency, ramp_up,
                                 hold_for):
    execution = [
        {
            "ramp-up": ramp_up,
            "hold-for": hold_for,
            "scenario": test_name
        }
    ]
    simple_scenario = {
        "execution": execution,
        "scenarios": {
            test_name: {
                "requests": [
                    {
                        "url": target_url,
                        "method": "GET",
                        "body": {},
                        "headers": {}
                    }
                ]
            }
        }
    }

    jmeter_scenario = {
        "execution": execution,
        "scenarios": {
            test_name: {
                "script": f"{test_id}.jmx"
            }
        }
    }

    scenario = simple_scenario if test_type == "simple" else jmeter_scenario
    payload = {
        "testId": test_id,
        "testName": test_name,
        "testDescription": test_name,
        "testTaskConfigs": [
            {
                "region": region,
                "taskCount": int(task_count),
                "concurrency": int(concurrency)
            }
        ],
        "testScenario": scenario,
        "showLive": json.loads("false"),  # Set showLive to false with correct JSON syntax
        "testType": test_type,
        "regionalTaskDetails": {
            region: {

            }
        },
    }
    if test_type == "jmeter":
        payload["fileType"] = "script"

    return payload


# Define the 'report_portal' function
def report_portal(endpoint,
                  project,
                  token,
                  launch_name,
                  launch_doc,
                  dlt_alias,
                  dlt_test_id,
                  expected_success_rate,
                  success_rate,
                  p95_0,
                  errors,
                  success_p95_0,
                  status):
    client = RPClient(endpoint=endpoint, project=project,
                      api_key=token)
    client.start()

    client.start_launch(
        name=launch_name,
        start_time=timestamp(),
        description=launch_doc,
    )

    item_id = client.start_test_item(
        name="DLT-Test",
        description=f"DLT-Test-UI: [https://{dlt_alias}/details/{dlt_test_id}](https://{dlt_alias}/details/{dlt_test_id})",
        start_time=timestamp(),
        item_type="STEP",
        parameters={
            "Expected Success Rate": expected_success_rate,
            "Success Rate": success_rate,
            "ERRORS": errors,
            "P95 Result": p95_0,
            "SUCCESS_P95": success_p95_0,
        },
    )

    client.finish_test_item(item_id=item_id, end_time=timestamp(), status=status)

    # Finish launch.
    client.finish_launch(end_time=timestamp())

    # Call terminate() to avoid losing data.
    client.terminate()


def main():
    host = os.environ.get('DLT_API_HOST').split('/')[2]
    dlt_alias = os.environ.get('DLT_ALIAS')
    region = os.environ.get('AWS_REGION')
    username = os.environ.get('COGNITO_USER')
    password = os.environ.get('COGNITO_PASSWORD')
    user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
    client_id = os.environ.get('COGNITO_CLIENT_ID')
    identity_pool_id = os.environ.get('COGNITO_IDENTITY_POOL_ID')
    client = boto3.client('cognito-idp', region_name=region)
    test_type = os.environ.get('TEST_TYPE', 'simple')  # Default test type is 'simple'
    test_id = os.environ.get('TEST_ID')
    test_name = os.environ.get('TEST_NAME')
    app_target_url = os.environ.get('APP_TARGET_URL')
    task_count = os.environ.get('TASK_COUNT')
    concurrency = os.environ.get('CONCURRENCY')
    ramp_up = os.environ.get('RAMP_UP')
    hold_for = os.environ.get('HOLD_FOR')

    # Report Portal
    endpoint = os.environ.get('RP_ENDPOINT')
    project = os.environ.get('RP_PROJECT')
    token = os.environ.get('RP_TOKEN')  # You can get UUID from user profile page in the Report Portal.
    launch_name = test_name
    launch_doc = test_name

    # Initiate authentication
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

    id_p = f'cognito-idp.{region}.amazonaws.com/{user_pool_id}'

    result = cognito_identity_client.get_id(
        IdentityPoolId=identity_pool_id,
        Logins={
            id_p: id_token
        },
    )

    identity_id = result['IdentityId']

    result = cognito_identity_client.get_credentials_for_identity(
        IdentityId=identity_id,
        Logins={
            id_p: id_token
        },
    )

    payload = create_test_scenario_payload(test_type, app_target_url, region, test_id, test_name, task_count,
                                           concurrency, ramp_up, hold_for)

    url = f"https://{host}/prod/scenarios"
    creds = ReadOnlyCredentials(
        result['Credentials']['AccessKeyId'], result['Credentials']['SecretKey'],
        result['Credentials']['SessionToken']
    )
    response = aws_sign_4_request(
        method='POST',
        url=url,
        creds=creds,
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

        # GET request to pull test status
        response = aws_sign_4_request(
            method='GET',
            url=f"{url}/{test_id}",
            creds=creds,
            region=region,
        )

        print(f'Test {test_id} has status > {response["status"]}', flush=True)
        if response['status'] != 'running':
            break

    # Check if the test is complete
    if response['status'] == 'complete':

        p95_0 = response['results']['total']['p95_0']
        success_p95_0 = os.environ.get('SUCCESS_P95', '1')  # Default to 1sec if not set
        expected_success_rate = os.environ.get('EXPECT_SUCCESS_RATE', '95')
        errors = response['results']['total']['fail']
        total = response['results']['total']['throughput']

        if total > 0:
            status = "PASSED"
            success_rate = int(100 - errors * 100 / total)
            if p95_0 is not None and float(p95_0) <= float(success_p95_0):
                print(
                    f'Test {test_id} passed successfully due to response time 95th percentile ({p95_0} < {success_p95_0})')

                if int(expected_success_rate) <= success_rate:
                    print(f'Test {test_id} passed successfully due to request count success rate '
                          f'({expected_success_rate} < {success_rate})')

                else:
                    status = "FAILED"
                    print(f'Test {test_id} failing build due to request count success rate '
                          f'(Success rate {success_rate} less then expected {expected_success_rate}')

            else:
                status = "FAILED"
                print(f'Test {test_id} failing build due to response time 95th percentile ({p95_0} > {success_p95_0})')

            report_portal(endpoint=endpoint, project=project, token=token, launch_name=launch_name,
                          launch_doc=launch_doc,
                          dlt_alias=dlt_alias, dlt_test_id=test_id, expected_success_rate=expected_success_rate,
                          success_rate=success_rate, p95_0=p95_0, errors=errors, success_p95_0=success_p95_0,
                          status=status)

            if status != "PASSED":
                exit(1)

    else:
        print(f'Test {test_id} failing build due to status {response["status"]}')
        exit(1)

    print(
        '\n' + f'For more information about the test, please, refer to the DLT WEB UI https://{dlt_alias}/details/{test_id}')


if __name__ == "__main__":
    main()
