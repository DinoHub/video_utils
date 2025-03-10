"""Video Getter using cv2"""
import os
import time
import logging
from collections import deque
from datetime import datetime
from threading import Thread

import cv2

logger = logging.getLogger(__name__)


class VideoStream:
    """
    Class that continuously gets frames from a cv2 VideoCapture object
    with a dedicated thread.
    """

    def __init__(
        self,
        video_feed_name,
        source_type,
        src,
        manual_video_fps,
        queue_size=3,
        recording_dir=None,
        reconnect_threshold_sec=20,
        do_reconnect=True,
        resize_fn=None,
        frame_crop=None,
        rtsp_tcp=True,
        max_cache=10,
    ):
        # rtsp_tcp argument does nothing here. only for vlc.
        self.video_stream_type = "cv2"
        self.video_feed_name = video_feed_name  # <cam name>
        self.source_type = source_type
        self.src = src  # <path>
        self.stream = cv2.VideoCapture(self.src)
        self.reconnect_threshold_sec = reconnect_threshold_sec
        self.do_reconnect = do_reconnect
        if not rtsp_tcp:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
        self.pauseTime = None
        self.printTime = None
        self.stopped = True
        self.Q = deque(
            maxlen=queue_size
        )  # Maximum size of a deque or None if unbounded.
        self.max_cache = max_cache
        self.resize_fn = resize_fn
        self.inited = False
        if manual_video_fps == -1:
            self.manual_video_fps = None
        else:
            self.manual_video_fps = manual_video_fps
        self.vidInfo = {}
        self.recording_dir = recording_dir

        if self.recording_dir is not None:
            self.record_source_video = True
            if not os.path.isdir(self.recording_dir):
                os.makedirs(self.recording_dir)
        else:
            self.record_source_video = False
        if frame_crop is not None:
            assert len(frame_crop) == 4, "Given FRAME CROP is invalid"
        self.frame_crop = frame_crop

        self.fps = None
        self.vid_width = None
        self.vid_height = None
        self.out_vid = None
        self.currentFrame = None

    def init_src(self):
        """init src"""
        try:
            self.stream = cv2.VideoCapture(self.src)
            if not self.manual_video_fps:
                self.fps = int(self.stream.get(cv2.CAP_PROP_FPS))
                if self.fps == 0:
                    logger.warning("cv2.CAP_PROP_FPS was 0. Defaulting to 30 fps.")
                    self.fps = 30
            else:
                self.fps = self.manual_video_fps
            # width and height returns 0 if stream not captured
            if self.frame_crop is None:
                self.vid_width = int(self.stream.get(3))
                self.vid_height = int(self.stream.get(4))
            else:
                l, t, r, b = self.frame_crop
                self.vid_width = r - l
                self.vid_height = b - t

            self.vidInfo = {
                "video_feed_name": self.video_feed_name,
                "height": self.vid_height,
                "width": self.vid_width,
                "manual_fps_inputted": self.manual_video_fps is not None,
                "fps": self.fps,
                "inited": False,
            }

            self.out_vid = None

            if self.vid_width != 0:
                self.inited = True
                self.vidInfo["inited"] = True

            self.__init_src_recorder()

        except Exception as error:
            logger.error("init stream %s error: %s", self.video_feed_name, error)

    def __init_src_recorder(self):
        """Init src_recorder"""
        if self.record_source_video and self.inited:
            now = datetime.now()
            day = now.strftime("%Y_%m_%d_%H-%M-%S")
            out_vid_fp = os.path.join(
                self.recording_dir, "orig_{}_{}.avi".format(self.video_feed_name, day)
            )
            self.out_vid = cv2.VideoWriter(
                out_vid_fp,
                cv2.VideoWriter_fourcc("M", "J", "P", "G"),
                int(self.fps),
                (self.vid_width, self.vid_height),
            )

    def start(self):
        """Start player"""
        if not self.inited:
            self.init_src()

        self.stopped = False

        t = Thread(target=self.get, args=())
        t.start()

        logger.info("Start video streaming for %s", self.video_feed_name)
        return self

    def reconnect_start(self):
        """Reconnet and start player"""
        s = Thread(target=self.reconnect, args=())
        s.start()
        return self

    def get(self):
        """Get frame"""
        while not self.stopped:
            try:
                # print('getting video' + str(time.time()))
                if len(self.Q) > self.max_cache:
                    time.sleep(0.01)
                    continue

                grabbed, frame = self.stream.read()

                if grabbed:
                    if self.frame_crop is not None:
                        l, t, r, b = self.frame_crop
                        frame = frame[t:b, l:r]

                    self.Q.appendleft(frame)

                    if self.record_source_video:
                        try:
                            self.out_vid.write(frame)
                        except Exception as e:
                            pass

                    time.sleep(1 / self.fps)

            except Exception as e:
                logger.warning("Stream %s grab error: %s", self.video_feed_name, e)
                grabbed = False

            if not grabbed:
                if self.pauseTime is None:
                    self.pauseTime = time.time()
                    self.printTime = time.time()
                    logger.info(
                        "No frames for %s, starting %.1fsec countdown",
                        self.video_feed_name,
                        self.reconnect_threshold_sec,
                    )
                time_since_pause = time.time() - self.pauseTime
                countdown_time = self.reconnect_threshold_sec - time_since_pause
                time_since_print = time.time() - self.printTime
                if (
                    time_since_print > 1 and countdown_time >= 0
                ):  # prints only every 1 sec
                    logger.debug(
                        "No frames for %s, countdown: %.1fsec",
                        self.video_feed_name,
                        countdown_time,
                    )
                    self.printTime = time.time()

                if countdown_time <= 0:
                    if self.do_reconnect:
                        self.reconnect_start()
                        break
                    if not self.more():
                        logger.info("Not reconnecting. Stopping..")
                        self.stop()
                        break
                    time.sleep(1)
                    logger.debug(
                        "Countdown reached but still have unconsumed frames in deque: %s",
                        len(self.Q),
                    )
                continue

            self.pauseTime = None

    def read(self):
        """Read next frame"""
        if self.more():
            self.currentFrame = self.Q.pop()
        if self.resize_fn:
            self.currentFrame = self.resize_fn(self.currentFrame)
        return self.currentFrame

    def more(self):
        """Checks if there are any more frames in the Queue"""
        return bool(self.Q)

    def stop(self):
        """Stop stream"""
        if not self.stopped:
            self.stopped = True
            time.sleep(0.1)

            if self.stream:
                self.stream.release()

            if self.more():
                self.Q.clear()

            if self.out_vid:
                self.out_vid.release()

            logger.info("Stopped video streaming for %s", self.video_feed_name)

    def reconnect(self):
        """Reconnect to stream"""
        logger.info("Reconnecting to %s ...", self.video_feed_name)
        if self.stream:
            self.stream.release()

        if self.more():
            self.Q.clear()

        while not self.stream.isOpened():
            logger.debug(str(datetime.now()), "Reconnecting to", self.video_feed_name)
            self.stream = cv2.VideoCapture(self.src)
        if not self.stream.isOpened():
            return "error opening {}".format(self.video_feed_name)

        if not self.inited:
            self.init_src()

        logger.info("VideoStream for %s initialised!", self.video_feed_name)
        self.pauseTime = None
        self.start()
