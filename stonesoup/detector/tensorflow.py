# -*- coding: utf-8 -*-
from pathlib import Path

import numpy as np
try:
    import tensorflow as tf
    from object_detection.utils import label_map_util as lm_util
except ImportError as error:
    raise ImportError(
        "Usage of the TensorFlow detectors requires that TensorFlow and the TensorFlow Object "
        "Detection API  are installed. A quick guide on how to set these up can be found here: "
        "https://tensorflow-object-detection-api-tutorial.readthedocs.io/en/latest/install.html")\
        from error

from ._video import _VideoAsyncDetector
from ..base import Property
from ..types.array import StateVector
from ..types.detection import Detection


class TensorFlowBoxObjectDetector(_VideoAsyncDetector):
    """TensorFlowBoxObjectDetector

    A box object detector that generates detections of objects in the form of bounding boxes 
    from image/video frames using a TensorFlow object detection model. Both TensorFlow 1 and 
    TensorFlow 2 compatible models are supported.
    
    The detections generated by the box detector have the form of bounding boxes that capture 
    the area of the frame where an object is detected. Each bounding box is represented by a 
    vector of the form ``[x, y, w, h]``, where ``x, y`` denote the relative coordinates of the 
    top-left corner, while ``w, h`` denote the relative width and height of the bounding box. 
    
    Additionally, each detection carries the following meta-data fields:

    - ``raw_box``: The raw bounding box, as generated by TensorFlow.
    - ``class``: A dict with keys ``id`` and ``name`` relating to the id and name of the 
      detection class.
    - ``score``: A float in the range ``(0, 1]`` indicating the detector's confidence.
    
    Important
    ---------
    Use of this class requires that TensorFlow 2 and the TensorFlow Object Detection API are 
    installed. A quick guide on how to set these up can be found 
    `here <https://tensorflow-object-detection-api-tutorial.readthedocs.io/en/latest/install.html>`_. 
    
    """  # noqa

    model_path: Path = Property(
        doc="Path to ``saved_model`` directory. This is the directory that contains the "
            "``saved_model.pb`` file.")

    labels_path: Path = Property(
        doc="Path to label map (``*.pbtxt`` file). This is the file that contains mapping of "
            "object/class ids to meaningful names")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load model
        model = tf.saved_model.load(self.model_path)
        tf_version = model.tensorflow_version

        # Get detection function
        if tf_version.startswith('1'):
            self._detect_fn = model.signatures['serving_default']
        else:
            self._detect_fn = model

        # Create category index
        self.category_index = lm_util.create_category_index_from_labelmap(self.labels_path,
                                                                          use_display_name=True)

    def _get_detections_from_frame(self, frame):
        # The input needs to be a tensor, convert it using `tf.convert_to_tensor`.
        input_tensor = tf.convert_to_tensor(frame.pixels)
        # The model expects a batch of images, so add an axis with `tf.newaxis`.
        input_tensor = input_tensor[tf.newaxis, ...]

        # Perform detection
        output_dict = self._detect_fn(input_tensor)

        # All outputs are batches tensors.
        # Convert to numpy arrays, and take index [0] to remove the batch dimension.
        # We're only interested in the first num_detections.
        num_detections = int(output_dict.pop('num_detections'))
        output_dict = {key: value[0, :num_detections].numpy()
                       for key, value in output_dict.items()}

        # Extract classes, boxes and scores
        classes = output_dict['detection_classes'].astype(np.int64)  # classes should be ints.
        boxes = output_dict['detection_boxes']
        scores = output_dict['detection_scores']

        # Form detections
        detections = set()
        frame_height, frame_width, _ = frame.pixels.shape
        for box, class_, score in zip(boxes, classes, scores):
            metadata = {
                "raw_box": box,
                "class": self.category_index[class_],
                "score": score
            }
            # Transform box to be in format (x, y, w, h)
            state_vector = StateVector([box[1]*frame_width,
                                        box[0]*frame_height,
                                        (box[3] - box[1])*frame_width,
                                        (box[2] - box[0])*frame_height])
            detection = Detection(state_vector=state_vector,
                                  timestamp=frame.timestamp,
                                  metadata=metadata)
            detections.add(detection)

        return detections
