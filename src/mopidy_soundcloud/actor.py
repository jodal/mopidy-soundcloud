from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar, override

import pykka
from mopidy import backend
from mopidy.types import Uri, UriScheme

from mopidy_soundcloud.library import SoundCloudLibraryProvider
from mopidy_soundcloud.soundcloud import SoundCloudClient

if TYPE_CHECKING:
    from mopidy.audio import AudioProxy
    from mopidy.config import Config

logger = logging.getLogger(__name__)


class SoundCloudBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes: ClassVar[list[UriScheme]] = [
        UriScheme("soundcloud"),
        UriScheme("sc"),
    ]

    @override
    def __init__(self, *, config: Config, audio: AudioProxy) -> None:
        super().__init__()
        self.config = config
        self.remote = SoundCloudClient(config)
        self.library = SoundCloudLibraryProvider(backend=self)
        self.playback = SoundCloudPlaybackProvider(audio=audio, backend=self)

    @override
    def on_start(self) -> None:
        username = self.remote.user.get("username")
        if username is not None:
            logger.info(f"Logged in to SoundCloud as {username!r}")


class SoundCloudPlaybackProvider(backend.PlaybackProvider):
    backend: SoundCloudBackend

    @override
    def translate_uri(self, uri: Uri) -> Uri | None:
        track_id = self.backend.remote.parse_track_uri(uri)
        track = self.backend.remote.get_track(track_id, True)  # noqa: FBT003
        if track is None:
            return None
        return track.uri
