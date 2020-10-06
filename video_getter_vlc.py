import os
import time
from collections import deque
from datetime import datetime
from threading import Thread

import cv2
import vlc

import video_getter_cv2


class VideoStream(video_getter_cv2.VideoStream):
    """
    Class that uses vlc instead of cv2 to continuously get frames with a dedicated thread as a workaround for artifacts.
    """

    def __init__(self, camName, src, isVideoFile=True, queueSize=5, writeDir=None, reconnectThreshold=20,
                 resize_fn=None):
        video_getter_cv2.VideoStream.__init__(self, camName, src, isVideoFile, queueSize, writeDir,
                                              reconnectThreshold,
                                              resize_fn)

        self.fixed_png_path = 'vlc_frame_{}.png'.format(camName)
        self.stream = cv2.VideoCapture(self.src)
        self.vlc_instance = vlc.Instance('--vout=dummy --aout=dummy')
        self.vlc_player = self.vlc_instance.media_player_new()
        self.vlc_player.set_mrl(self.src)

    def get(self):
        self.vlc_player.play()
        while not self.stopped:
            try:
                # print('getting video' + str(time.time()))
                res = self.vlc_player.video_take_snapshot(0, self.fixed_png_path, 0, 0)
                grabbed = (res >= 0)

                if grabbed:
                    frame = cv2.imread(self.fixed_png_path)
                    self.Q.appendleft(frame)

                    if self.record_tracks:
                        try:
                            self.out_vid.write(frame)
                        except Exception as e:
                            pass

                    if self.isVideoFile:
                        time.sleep(1 / self.fps)

            except Exception as e:
                print('stream grab error:{}'.format(e))
                grabbed = False

            if not grabbed:
                if self.pauseTime is None:
                    self.pauseTime = time.time()
                    self.printTime = time.time()
                    print('No frames for {}, starting {:0.1f}sec countdown to reconnect.'. \
                          format(self.camName, self.reconnectThreshold))
                time_since_pause = time.time() - self.pauseTime
                time_since_print = time.time() - self.printTime
                if time_since_print > 1:  # prints only every 1 sec
                    print('No frames for {}, reconnect starting in {:0.1f}sec'. \
                          format(self.camName, self.reconnectThreshold - time_since_pause))
                    self.printTime = time.time()

                if time_since_pause > self.reconnectThreshold:
                    self.reconnect_start()
                    break
                continue

            self.pauseTime = None

    def stop(self):
        if not self.stopped:
            self.stopped = True
            time.sleep(0.1)

            # if self.stream:
            # self.stream.release()

            if self.more():
                self.Q.clear()

            if self.vlc_player:
                self.vlc_player.stop()
                self.vlc_player.release()
                self.vlc_instance.release()

            if self.record_tracks and self.out_vid:
                self.out_vid.release()

            print('stop video streaming for {}'.format(self.camName))

    def reconnect(self):
        print('Reconnecting')

        if self.more():
            self.Q.clear()

        if self.vlc_player:
            self.vlc_player.stop()
            self.vlc_player.release()

        self.vlc_player = self.vlc_instance.media_player_new()
        self.vlc_player.set_mrl(self.src)

        if self.record_tracks and not self.inited:
            self.init_src()

        print('VideoStream for {} initialised!'.format(self.camName))
        self.pauseTime = None
        self.start()
