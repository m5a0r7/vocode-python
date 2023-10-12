from __future__ import annotations

import asyncio
import audioop
import logging

from opentelemetry import trace, metrics
from typing import Generic, TypeVar, Union, Optional
from vocode.streaming.models.audio_encoding import AudioEncoding
from vocode.streaming.models.model import BaseModel

from vocode.streaming.models.transcriber import TranscriberConfig
from vocode.streaming.utils.interrupt_model import InterruptModel
from vocode.streaming.utils.worker import AsyncWorker, ThreadAsyncWorker
from vocode.utils.context_tracker.factory import ContextTrackerFactory

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)


class Transcription(BaseModel):
    message: str
    confidence: float
    is_final: bool
    is_interrupt: bool = False

    def __str__(self):
        return f"Transcription({self.message}, {self.confidence}, {self.is_final})"


TranscriberConfigType = TypeVar("TranscriberConfigType", bound=TranscriberConfig)


class AbstractTranscriber(Generic[TranscriberConfigType]):
    def __init__(self, transcriber_config: TranscriberConfigType):
        self.transcriber_config = transcriber_config
        self.is_muted = False

    def mute(self):
        self.is_muted = True

    def unmute(self):
        self.is_muted = False

    def get_transcriber_config(self) -> TranscriberConfigType:
        return self.transcriber_config

    async def ready(self):
        return True

    def create_silent_chunk(self, chunk_size, sample_width=2):
        linear_audio = b"\0" * chunk_size
        if self.get_transcriber_config().audio_encoding == AudioEncoding.LINEAR16:
            return linear_audio
        elif self.get_transcriber_config().audio_encoding == AudioEncoding.MULAW:
            return audioop.lin2ulaw(linear_audio, sample_width)


class BaseAsyncTranscriber(AbstractTranscriber[TranscriberConfigType], AsyncWorker):
    def __init__(
            self,
            transcriber_config: TranscriberConfigType,
            logger: Optional[logging.Logger] = None,

    ):
        self.transcriber_config = transcriber_config
        self.logger = logger or logging.getLogger(__name__)
        self.interrupt_on_blockers: bool = self.transcriber_config.interrupt_on_blockers
        if self.interrupt_on_blockers:
            self.interrupt_model: InterruptModel = InterruptModel(logger=self.logger)
            self.interrupt_model_initialize_task = asyncio.create_task(
                self.interrupt_model.initialize_embeddings()
            )
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.output_queue: asyncio.Queue[Transcription] = asyncio.Queue()
        context_tracker_factory = ContextTrackerFactory()
        self.context_tracker = context_tracker_factory.create_context_tracker(
            transcriber_config.context_tracker_config, logger)
        AsyncWorker.__init__(self, self.input_queue, self.output_queue)
        AbstractTranscriber.__init__(self, transcriber_config)

    async def _run_loop(self):
        raise NotImplementedError

    def send_audio(self, chunk):
        if not self.is_muted:
            self.consume_nonblocking(chunk)
        else:
            self.consume_nonblocking(self.create_silent_chunk(len(chunk)))

    def terminate(self):
        AsyncWorker.terminate(self)


class BaseThreadAsyncTranscriber(
    AbstractTranscriber[TranscriberConfigType], ThreadAsyncWorker
):
    def __init__(
            self,
            transcriber_config: TranscriberConfigType,
    ):
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.output_queue: asyncio.Queue[Transcription] = asyncio.Queue()
        ThreadAsyncWorker.__init__(self, self.input_queue, self.output_queue)
        AbstractTranscriber.__init__(self, transcriber_config)

    def _run_loop(self):
        raise NotImplementedError

    def send_audio(self, chunk):
        if not self.is_muted:
            self.consume_nonblocking(chunk)
        else:
            self.consume_nonblocking(self.create_silent_chunk(len(chunk)))

    def terminate(self):
        ThreadAsyncWorker.terminate(self)


BaseTranscriber = Union[
    BaseAsyncTranscriber[TranscriberConfigType],
    BaseThreadAsyncTranscriber[TranscriberConfigType],
]
