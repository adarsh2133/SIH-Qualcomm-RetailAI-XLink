# Footfall person model

This directory contains an Ultralytics YOLOv8n model exported for NCNN at
320x320 from the general COCO pretrained weights. COCO class ID `0` is
`person`. The model was exported with Ultralytics 8.4.132; see `metadata.yaml`
for the full COCO class map and model metadata.

The model metadata declares the **AGPL-3.0** license. Review that license and
obtain any required commercial license before using or distributing this
model in a commercial deployment. This general upright-person model is a
baseline only and has not been validated for the project's overhead camera or
dense crowds.

On the Raspberry Pi, configure
`PORTAL_FOOTFALL_PERSON_MODEL_PATH=/home/xlink/PORTAL-XLINK/models/footfall-person-ncnn`
and `PORTAL_FOOTFALL_PERSON_CLASS_ID=0`, then restart the service. The Pi
runtime expects the matching `model.ncnn.param` and `model.ncnn.bin` files.
