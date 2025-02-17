import logging
from typing import Optional

from vocode.streaming.telephony.noise_canceler.base_noise_canceler import BaseNoiseCanceler
from vocode.streaming.telephony.noise_canceler.noise_canceling import NoiseCancelingConfig, NoiseCancelingType


class RRNWrapperNoiseCancelingConfig(NoiseCancelingConfig, type=NoiseCancelingType.RRN_WRAPPER.value):
    sample_rate: int = 8000
    library_name: str = "librnnoise_default.so.0.4.1"


class RRNWrapperNoiseCanceler(BaseNoiseCanceler[RRNWrapperNoiseCancelingConfig]):
    def __init__(self, noise_canceling_config: RRNWrapperNoiseCancelingConfig, logger: Optional[logging.Logger] = None):
        super().__init__(noise_canceling_config, logger)
        from rnnoise_wrapper import RNNoise
        self.denoiser = RNNoise(self.noise_canceling_config.library_name)

    def cancel_noise(self, audio: bytes) -> bytes:
        out = self.denoiser.filter(audio, sample_rate=self.noise_canceling_config.sample_rate)
        return out
