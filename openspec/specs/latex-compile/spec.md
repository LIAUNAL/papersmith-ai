# LaTeX Compile Specification

## Purpose

Compiling the project locally and reporting reliable status and diagnostics. Structure MUST keep a later cloud deployment possible through ports.

## Requirements

### Requirement: Local compile

The system MUST compile the project's main document with the locally installed TeX engine and produce a PDF on success.

#### Scenario: Successful compile

- GIVEN a valid project
- WHEN the user starts a compile
- THEN a PDF is produced and the status is success

### Requirement: Status from diagnostics

Compile status MUST be derived from reported error diagnostics and PDF presence, and MUST NOT rely on the process exit code alone.

#### Scenario: Zero exit with errors

- GIVEN the engine exits 0 and writes a PDF but reports `error: main.tex:12: <message>`
- WHEN the run ends
- THEN the status is failed-with-errors and the diagnostic is listed

#### Scenario: Halt on error

- GIVEN stop-on-error is on and the engine halts with exit 1 and no PDF
- WHEN the run ends
- THEN the status is failed and the first error is shown with file and line

### Requirement: Stop-on-error toggle

The user MUST be able to toggle between halting at the first error and continuing past errors. The toggle MUST default to continuing past errors and MUST persist per project.

#### Scenario: Continue past errors

- GIVEN stop-on-error is off and the source has two errors
- WHEN the user compiles
- THEN both errors are listed and the produced PDF is previewable

#### Scenario: Toggle default and persistence

- GIVEN a new project
- WHEN the toggle is read
- THEN it is set to continue past errors
- AND a changed value is restored after reload

### Requirement: Diagnostics

Errors parsed as `file:line: message` from engine error output MUST be reported, and warnings (such as undefined references) MUST be read from the kept log and reported distinctly from errors.

#### Scenario: Undefined reference warning

- GIVEN the log contains an undefined-reference warning and no errors
- WHEN the run ends
- THEN the status is success and the warning is listed as a warning

### Requirement: First-run state

The UI MUST show a distinct state while support files are being downloaded on first compile.

#### Scenario: First compile

- GIVEN support files are not cached
- WHEN a compile starts
- THEN the UI shows a "preparing/downloading support files" state, distinct from normal compiling

#### Scenario: Offline first run

- GIVEN support files are uncached and no network is available
- WHEN a compile starts
- THEN a readable error explains the download failure

### Requirement: BibTeX and biblatex

BibTeX bibliographies MUST compile. A project requiring biblatex with biber MUST produce a clear diagnostic that it is unsupported.

#### Scenario: BibTeX paper

- GIVEN a project using `\bibliography` and a `.bib` file
- WHEN compiled
- THEN citations resolve in the PDF

#### Scenario: biblatex with biber

- GIVEN a project using the biblatex package with the biber backend
- WHEN compiled
- THEN a notice states biber is unsupported

### Requirement: Shell escape disabled

Shell escape MUST stay disabled. The UI SHOULD disclose that compiling does not confine file reads to the project.

#### Scenario: Shell escape attempt

- GIVEN a document using `\write18`
- WHEN compiled
- THEN no shell command runs

### Requirement: Single run and cancel

The system MUST allow one compile at a time per project and MUST let the user cancel a running compile. A request made while a compile runs MUST be queued as a single follow-up, and cancel MUST also discard the queued request.

#### Scenario: Overlapping request

- GIVEN a compile is running
- WHEN another compile is requested, even several times
- THEN exactly one follow-up is queued and nothing runs concurrently

#### Scenario: Cancel discards queue

- GIVEN a running compile with a queued follow-up
- WHEN the user cancels
- THEN the run stops and the queued request is discarded

### Requirement: Time limit

A compile MUST be terminated after 180 seconds, extended to 600 seconds while support files are downloading.

#### Scenario: Timeout

- GIVEN a compile exceeds 180 seconds without downloading
- WHEN the limit is reached
- THEN the run is terminated and reported as timed out

#### Scenario: Extended during download

- GIVEN a first compile downloading support files
- WHEN 180 seconds pass
- THEN the run continues until 600 seconds

### Requirement: Auto-compile

The system SHOULD compile automatically shortly after a successful save, and the user MUST be able to turn this off.

#### Scenario: Compile after save

- GIVEN auto-compile is on
- WHEN a save succeeds
- THEN a compile starts shortly after

#### Scenario: Auto-compile off

- GIVEN auto-compile is off
- WHEN a save succeeds
- THEN no compile starts

### Requirement: Outside-project read diagnostic

When the engine reads a file outside the project, the system SHOULD report a warning naming that file.

#### Scenario: Outside read

- GIVEN a document including a file outside the project root
- WHEN compiled
- THEN a warning names that file

### Requirement: Sandboxed compile

When a supported OS sandbox is detected, the user MAY enable sandboxed compilation; it MUST be off by default and a sandbox start failure MUST be reported with an option to disable it.

#### Scenario: Off by default

- GIVEN a supported sandbox is detected
- WHEN a new project is compiled
- THEN sandboxed compilation is not used

#### Scenario: Sandbox start failure

- GIVEN sandboxed compilation is enabled and the sandbox fails to start
- WHEN a compile runs
- THEN the failure is reported with an option to disable sandboxed compilation
