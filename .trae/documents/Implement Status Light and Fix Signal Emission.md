I will implement the status light and fix the signal syntax error.

### Plan
1.  **Fix `SerialWorker.py`**:
    *   Correct the syntax error on line 194: `self.sigReplyOk(...)` to `self.sigReplyOk.emit(...)`.
2.  **Update `MainWindow.py`**:
    *   Add a `QLabel` named `lblStatus` to the toolbar to serve as the status light.
    *   Set the initial style of `lblStatus` to Red (disconnected).
    *   Implement logic to change the color of `lblStatus`:
        *   **Green**: On successful connection (`_onConnected`).
        *   **Red**: On disconnection (`_onDisconnect`) or reply mismatch (`_onReplyMismatch`).
        *   **Yellow**: When a frame is sent (`_onFrameSent`).
        *   **Blue**: When a valid reply is received (`_onReplyOk`).
    *   Connect the new `sigReplyOk` and `sigReplyMismatch` signals from `SerialWorker` to corresponding slots in `MainWindow`.
