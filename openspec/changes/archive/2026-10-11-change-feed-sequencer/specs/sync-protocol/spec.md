# Spec Delta

## ADDED Requirements

### Requirement: Changes in commit order
Change sequence numbers SHALL be assigned in the order in which the changes became committed, so that a client that has received a number never misses a change with a smaller number.

#### Scenario: Overlapping transactions
- **WHEN** a long transaction starts before a short one but commits after it
- **THEN** the change of the short transaction receives the smaller change sequence number
- **AND** a client resuming after the short transaction's change still receives the long transaction's change

### Requirement: Revocation across server processes
When an installation runs several server processes, signing out a device or deactivating an account through one process SHALL take effect in all processes within one second.

#### Scenario: Sign-out on another process
- **WHEN** a device is signed out through server process A
- **THEN** server process B rejects that device's next request within one second
