import numpy as np


class VideoManager:
    def __init__(self, camNames, streams, queueSize=5, writeDir=None, reconnectThreshold=20, max_height=720,
                 isVideoFile=True, method='cv2'):
        self.max_height = max_height
        self.num_vid_streams = len(streams)
        self.stopped = True

        assert len(streams) == len(camNames), 'streams and camNames should be the same length'
        self.videos = []

        if (method == 'cv2'):
            from video_getter_cv2 import VideoStream
        elif (method == 'vlc'):
            from video_getter_vlc import VideoStream

        for i, camName in enumerate(camNames):
            stream = VideoStream(camName, streams[i], queueSize=queueSize, writeDir=writeDir,
                                 reconnectThreshold=reconnectThreshold, isVideoFile=isVideoFile)

            self.videos.append({'camName': camName, 'stream': stream})

    # def _resize(self, frame):
    # 	height, width = frame.shape[:2]
    # 	if height != self.resize_height or width != self.resize_width:
    # 		# print("Resizing from {} to {}".format((height, width), (resize_height, resize_width)))
    # 		frame = cv2.resize(frame, (self.resize_width, self.resize_height))
    # 	return frame

    def start(self):
        if self.stopped:
            # print('vid manager start')
            for vid in self.videos:
                vid['stream'].start()

            self.stopped = False

    def stop(self):
        if not self.stopped:
            # print('vid manager stop')
            self.stopped = True
            # time.sleep(1)

            for vid in self.videos:
                vid['stream'].stop()

    def update_info(self):
        for i, vid in enumerate(self.videos):
            vid['info'] = vid['stream'].vidInfo

    def getAllInfo(self):
        all_info = []
        for vid in self.videos:
            all_info.append(vid['stream'].vidInfo)
        return all_info

    def read(self):
        statuses = []
        frames = []

        for vid in self.videos:
            if not vid['stream'].more():
                frames.append([])
                statuses.append(False)
            else:
                frame = vid['stream'].read()
                frames.append(frame)
                statuses.append(True)

        return statuses, frames
