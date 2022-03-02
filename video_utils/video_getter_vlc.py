"""Video Getter using VLC"""
from datetime import datetime
import logging
import os
import time

import cv2
import vlc  # pylint: disable=import-error

from . import video_getter_cv2

logger = logging.getLogger(__name__)


class VideoStream(video_getter_cv2.VideoStream):
    """
    Class that uses vlc instead of cv2 to continuously get frames with a dedicated thread as a workaround for artifacts.
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
    ):
        video_getter_cv2.VideoStream.__init__(
            self,
            video_feed_name,
            source_type,
            src,
            manual_video_fps,
            queue_size=queue_size,
            recording_dir=recording_dir,
            reconnect_threshold_sec=reconnect_threshold_sec,
            do_reconnect=do_reconnect,
            resize_fn=resize_fn,
            frame_crop=frame_crop,
            rtsp_tcp=rtsp_tcp,
        )

        self.video_stream_type = "vlc"

        self.fixed_png_path = f"temp_vlc_frame_{video_feed_name}.png"
        vlc_flags = "--vout=dummy --aout=dummy"
        if rtsp_tcp:
            vlc_flags += " --rtsp-tcp"
        self.vlc_instance = vlc.Instance(vlc_flags)
        self.vlc_player = self.vlc_instance.media_player_new()

        if self.record_source_video:
            now = datetime.now()
            day = now.strftime("%Y_%m_%d_%H-%M-%S")
            out_vid_fp = os.path.join(
                self.recording_dir, "orig_{}_{}.mp4".format(self.video_feed_name, day)
            )
            self.vlc_media = self.vlc_instance.media_new(
                self.src,
                f"sout=#duplicate{{dst=display,dst=std{{access=file,mux=ts,dst={out_vid_fp}}}",
            )
        else:
            self.vlc_media = self.vlc_instance.media_new(self.src)

        self.vlc_player.set_media(self.vlc_media)

    def __init_src_recorder(self):
        """Init src_recorder and to disable video_getter_cv2 cv2.VideoWriter"""

    def get(self):
        """Get frame"""
        self.vlc_player.play()
        # Known Issue: This needs to be called again after "play()" for the video feed to start coming in,
        # unable to figure out why
        self.vlc_player = self.vlc_instance.media_player_new()
        self.vlc_player.set_mrl(self.src)
        self.vlc_player.play()

        while not self.stopped:
            try:
                res = self.vlc_player.video_take_snapshot(0, self.fixed_png_path, 0, 0)
                grabbed = res >= 0

                if grabbed:
                    frame = cv2.imread(self.fixed_png_path)
                    if self.frame_crop is not None:
                        l, t, r, b = self.frame_crop
                        frame = frame[t:b, l:r]

                    self.Q.appendleft(frame)

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

    def stop(self):
        """Stop stream"""
        if not self.stopped:
            self.stopped = True
            time.sleep(0.1)

            if self.more():
                self.Q.clear()

            if self.vlc_player:
                self.vlc_player.stop()
                self.vlc_player.release()
                self.vlc_instance.release()

            logger.info("Stopped video streaming for %s", self.video_feed_name)

    def reconnect(self):
        """Reconnect to stream"""
        logger.info("Reconnecting to %s ...", self.video_feed_name)
        if self.more():
            self.Q.clear()

        if self.vlc_player:
            self.vlc_player.stop()
            self.vlc_player.release()

        # Known Issue: This needs to be called again after "play()" for the video feed to start coming in,
        # unable to figure out why
        self.vlc_player = self.vlc_instance.media_player_new()
        self.vlc_player.set_mrl(self.src)

        if not self.inited:
            self.init_src()

        logger.info("VideoStream for %s initialised!", self.video_feed_name)
        self.pauseTime = None
        self.start()
