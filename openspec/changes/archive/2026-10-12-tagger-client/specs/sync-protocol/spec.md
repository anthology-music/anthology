# Spec Delta

## ADDED Requirements

### Requirement: Service availability
The server SHALL offer a `services` subscription to all signed-in users that lists the services the installation uses (e.g. the tagger) with their status (available, unavailable, incompatible), and SHALL send a delta when a status changes, so that clients can hide features of unavailable services.

#### Scenario: Tagger stops
- **WHEN** the tagger stops while a client is subscribed to `services`
- **THEN** the client receives a delta marking the tagger as unavailable within 30 seconds
