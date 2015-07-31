import pytest

from labrad import crypto


def test_fingerprint():
    """Verify that fingerprint matches what we get from openssl.

    To get the fingerprint of a certificate with openssl, you can do:
    $ openssl x509 -fingerprint -in <certfile>
    """
    cert = """
    -----BEGIN CERTIFICATE-----
    MIICqjCCAZKgAwIBAgIILDVF+J1HIWowDQYJKoZIhvcNAQELBQAwFDESMBAGA1UE
    AwwJbG9jYWxob3N0MCAXDTE0MDgyODE3MTUyM1oYDzk5OTkxMjMxMjM1OTU5WjAU
    MRIwEAYDVQQDDAlsb2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEK
    AoIBAQCVPL4WfLACl/oR+RNolkwxfyxcj8IdTrzrUXmY1zBBncdHhHOPijJZHdP5
    vmD4HO2kb793V4uT02gnMq+MiYr8fNui7yRYnInG3GsgwJKQTH/5objHN6JZl505
    82r/aas0rDjRRc25WXGSCuPuW+h1u0f2N4PuBwN6iCmv0FDhEz7C3FgDWDSk4heY
    xLglX2wnkrD4nob4NXWqX7VZ5A9KYBKQPhpOczg+vtv1nd3CnU5JN9GbC3AZ+4wF
    Zb0xMpLDgn4T5z0TjOhJOwCbDOSsJWdC0q6UQe4ln5GubzKjPaJWVR4VXOsVuqoU
    q4fLed5vHSsQUc0C6qElvak0xULbAgMBAAEwDQYJKoZIhvcNAQELBQADggEBACVZ
    H5UJfpvujJ5tV0Mj9Jho0f5Wf/KARTa/5NL6lbM3KPSrrOZGdnH2Hag6me3JMJ+y
    kpxCc5HQnhF+Ep21Y5tFo0Ex2/FRGSfxZZVL0ERjMYnJpzjbnB4S5VPYW1LB+ctL
    +kwNc+sc8up986zNZnzxRY5hllvmC82Bn24dCVECzy3fgczVpOSh4pLeF+sXYOA1
    2ZT081GtWsEjebCndRoTtInTkqdtsSLHvznAi8YQ7lhtow/sAr5hbUaGwdrROUaq
    6Z+dzh7LHrTmfqmefNGGqi+hWKSU+fxGYQ+QDUjCD5J1dfnnueeHgYIeiQ9ZjnyE
    f3brW92sWUeqydhqD5A=
    -----END CERTIFICATE-----
    """
    expected_fingerprint = "5E:DF:14:6E:87:0F:2D:15:FD:B2:07:4E:6B:43:9A:21:84:58:F7:70"
    assert crypto.fingerprint(cert) == expected_fingerprint


if __name__ == '__main__':
    pytest.main(['-v', __file__])
