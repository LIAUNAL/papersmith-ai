# Delta for Local Server Security

## ADDED Requirements

### Requirement: Credential routes are write-only

Credential routes MUST accept a key only through a JSON body, MUST require the launch token like every other route, and MUST NOT return a key in any response. Responses MUST carry only set or not set and at most the last four characters. Keys MUST NOT appear in URLs, headers returned to the client, or server logs.

#### Scenario: Save and echo check

- GIVEN a valid token and a JSON body with a key
- WHEN the key is saved
- THEN the response contains no key and at most the last four characters

#### Scenario: Missing token

- GIVEN a credential request without the launch token
- WHEN received
- THEN it is rejected and the store is unchanged

#### Scenario: Wrong content type or foreign origin

- GIVEN a credential write declaring a form content type, or carrying a foreign Origin
- WHEN received
- THEN it is rejected and the store is unchanged

#### Scenario: Read-back route probing

- GIVEN a stored key
- WHEN any GET, error path or malformed request touches a credential route
- THEN no response body, header or log line contains the key
