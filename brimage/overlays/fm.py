import logging

import numpy as np
from scipy.signal import butter, filtfilt

from brimage.glitchcore.helper import remap
from brimage.overlays.base_overlay import BaseOverlay
from brimage.clib.algorithms import freqmod_row

logger = logging.getLogger(__name__)


def _butter_lowpass(cutoff, fs, order=5):
    """ calculates the butterworth lowpass filter """
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype="low", analog=False)
    return b, a


def _butter_lowpass_filter(data, cutoff, fs, order=5):
    """ applies a butterworth lowpass filter """
    b, a = _butter_lowpass(cutoff, fs, order=order)
    y = filtfilt(b, a, data)
    return y


class FreqModOverlay(BaseOverlay):
    """ Frequncy Modulation Overlay """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_phase = 0
        self.max_phase = 0

        self.greyscale = False
        self.omega = 0
        self.quantization = 0

    def map_algorithm(self, **kwargs):
        """ calculates frequency modulation and imposes it on the return image """
        # unpack arguments
        greyscale = kwargs.get("greyscale", True)
        numdevs = kwargs.get("numdevs", 0)
        lowpass = kwargs.get("lowpass", 0)

        img = self._get_from_feed("RGB")
        self.greyscale = greyscale
        self._set_hyper_parameters(**kwargs)

        logger.debug(
            f"FreqModOverlay@{id(self)}: adjusted omega: {self.omega}, adjusted phase: {self.max_phase}, lowpass: {lowpass}, pquantize: {self.quantization}, numdevs: {numdevs}"
        )

        logger.debug("Image shape {}".format(img.shape))

        if greyscale:
            logger.debug("Greyscale")
            img = np.mean(img, axis=2)

            self.image = self._apply_to(img, lowpass)
            if numdevs > 0:
                self.image = self._take_distribution(self.image, numdevs)
        else:
            logger.debug("Colour")
            image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            for i in range(img.shape[-1]):
                print(f"Processing channel {i}")
                channel = img[:, :, i]
                channel = self._apply_to(channel, lowpass)

                if numdevs > 0:
                    channel = self._take_distribution(channel, numdevs)

                image[..., i] = channel
            self.image = image

        return self.image

    def _take_distribution(self, layer, numdevs):
        """ map mean + (stds_from_mean) * std to 255, otherwise 0 in image """

        _mean = np.mean(layer)
        _std = np.std(layer)

        layer = np.where(
            layer > _mean + numdevs * _std,
            255,
            0,
        )
        return np.array(layer, dtype=np.uint8)

    def _apply_to(self, channel, lowpass):
        """ applies the FM algorithm to a specific channel """
        logger.debug("applying frequency modulation")
        new_channel = []
        for row in channel:
            row = freqmod_row(row, self.width, self.max_phase, self.omega)
            if lowpass > 0.000001:  # float comparsison check
                row = self._lowpass(row, lowpass)
            new_channel.append(row)

        logger.debug("frequency modulation done")

        new_channel = np.array(new_channel)
        new_channel = remap(
            new_channel, np.min(new_channel), np.max(new_channel), 0, 255
        )
        return np.array(new_channel)

    def _lowpass(self, row, amount):
        """ apply a lowpass filter to the row """
        order = 6
        freq_sample = 30
        cutoff = amount * freq_sample
        return _butter_lowpass_filter(row, cutoff, freq_sample, order)

    def _set_hyper_parameters(self, **kwargs):
        """ sets the necessary phase and omega values """
        # unpack values
        omega = kwargs.get("omega", 0.1)
        phase = kwargs.get("phase", 0.1)
        quantization = kwargs.get("quantization", 0)

        omega = remap(
            omega,
            0,
            1,
            2 * np.pi / (0.5 * self.width),
            2 * np.pi / (0.005 * self.width),
        )
        phase = remap(phase, 0, 1, 0, 2 * np.pi)

        self.omega = omega
        self.max_phase = phase
        self.min_phase = -phase
        self.quantization = quantization

    def post_quantize(self, quant):
        """ apply quantization after the image has been generated """
        image = np.round_(remap(self._image, 0, 255, 0, quant))
        self._image = remap(image, 0, quant, 0, 255)
