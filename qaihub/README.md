# QAI Hub utilities

These utilities describe the offline deployment boundary; they do not provide
an inference runtime or pretend to export/compile/profile a model. A production model must be exported/compiled in
Qualcomm AI Hub or the required Qualcomm tooling, validated for the target
chipset, and copied to the device before runtime use. The application loads a
local validated artifact through the QNN Execution Provider when available.
It does not download models or require AI Hub credentials during inference.

The repository does not specify a Qualcomm chipset and does not include a
validated model artifact. Replace the stubs under `models/qualcomm/` and
configure `PORTAL_QUALCOMM_MODEL_PATH` before claiming Qualcomm inference is
available.
