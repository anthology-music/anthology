# Spec Delta

## ADDED Requirements

### Requirement: Revocation of media access
Signing out a device SHALL invalidate all signed media URLs issued for that device, and deactivating a user SHALL invalidate all signed media URLs issued for that user, effective immediately and before the URLs expire.

#### Scenario: Lost phone signed out
- **WHEN** a user signs out a lost phone in "My devices"
- **THEN** media requests with URLs issued for that phone are rejected immediately

#### Scenario: User deactivated
- **WHEN** an admin deactivates a user
- **THEN** media requests with URLs issued for that user are rejected immediately
