from __future__ import annotations

import collections
import logging
import re
import urllib.parse
from typing import TYPE_CHECKING, Any, override

from mopidy import backend
from mopidy.models import Ref, SearchResult, Track
from mopidy.types import SearchQuery, Uri

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mopidy_soundcloud.actor import SoundCloudBackend

logger = logging.getLogger(__name__)


def generate_uri(path) -> Uri:
    return Uri(f"soundcloud:directory:{urllib.parse.quote('/'.join(path))}")


def new_folder(name, path):
    return Ref.directory(uri=generate_uri(path), name=name)


def simplify_search_query(query):
    if isinstance(query, dict):
        r = []
        for v in query.values():
            if isinstance(v, list):
                r.extend(v)
            else:
                r.append(v)
        return " ".join(r)
    if isinstance(query, list):
        return " ".join(query)
    return query


class SoundCloudLibraryProvider(backend.LibraryProvider):
    backend: SoundCloudBackend

    root_directory = Ref.directory(
        uri=Uri("soundcloud:directory"),
        name="SoundCloud",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.vfs = {"soundcloud:directory": {}}
        self._add_to_vfs(new_folder("Following", ["following"]))
        self._add_to_vfs(new_folder("Liked", ["liked"]))
        self._add_to_vfs(new_folder("Sets", ["sets"]))
        self._add_to_vfs(new_folder("Stream", ["stream"]))

    def _add_to_vfs(self, _model):
        self.vfs["soundcloud:directory"][_model.uri] = _model

    def _list_sets(self):
        sets_vfs = collections.OrderedDict()
        for name, set_id, _tracks in self.backend.remote.get_sets():
            sets_list = new_folder(name, ["sets", set_id])
            logger.debug(f"Adding set {sets_list.name} to VFS")
            sets_vfs[set_id] = sets_list
        return list(sets_vfs.values())

    def _list_liked(self):
        vfs_list = collections.OrderedDict()
        for track in self.backend.remote.get_likes():
            logger.debug(f"Adding liked track {track.name} to VFS")
            vfs_list[track.name] = Ref.track(uri=track.uri, name=track.name)
        return list(vfs_list.values())

    def _list_user_follows(self):
        sets_vfs = collections.OrderedDict()
        for name, user_id in self.backend.remote.get_followings():
            sets_list = new_folder(name, ["following", user_id])
            logger.debug(f"Adding set {sets_list.name} to VFS")
            sets_vfs[user_id] = sets_list
        return list(sets_vfs.values())

    def _tracklist_to_vfs(self, track_list):
        vfs_list = collections.OrderedDict()
        for temp_track in track_list:
            if not isinstance(temp_track, Track):
                temp_track = self.backend.remote.parse_track(temp_track)  # noqa: PLW2901
            if temp_track is not None:
                vfs_list[temp_track.name] = Ref.track(
                    uri=temp_track.uri, name=temp_track.name
                )
        return list(vfs_list.values())

    @override
    def browse(self, uri: Uri) -> list[Ref]:  # noqa: PLR0911
        if not self.vfs.get(uri):
            match = re.match(r".*:(\w*)(?:/(\d*))?", uri)
            if match is None:
                return []
            (req_type, res_id) = match.groups()
            # Sets
            if req_type == "sets":
                if res_id:
                    return self._tracklist_to_vfs(self.backend.remote.get_set(res_id))
                return self._list_sets()
            # Following
            if req_type == "following":
                if res_id:
                    return self._tracklist_to_vfs(
                        self.backend.remote.get_tracks(res_id)
                    )
                return self._list_user_follows()
            # Liked
            if req_type == "liked":
                return self._list_liked()
            # User stream
            if req_type == "stream":
                return self._tracklist_to_vfs(self.backend.remote.get_user_stream())

        # root directory
        return list(self.vfs.get(uri, {}).values())

    @override
    def search(
        self,
        query: SearchQuery,
        uris: Iterable[Uri] | None = None,
        exact: bool = False,
    ) -> SearchResult | None:
        # TODO: Support exact search

        if not query:
            return None

        if "uri" in query:
            search_query = "".join(str(query["uri"]))
            url = urllib.parse.urlparse(search_query)
            if "soundcloud.com" not in url.netloc:
                return None
            logger.info(f"Resolving SoundCloud for: {search_query}")
            return SearchResult(
                uri=Uri("soundcloud:search"),
                tracks=self.backend.remote.resolve_url(search_query),
            )
        search_query = simplify_search_query(query)
        logger.info(f"Searching SoundCloud for: {search_query}")
        return SearchResult(
            uri=Uri("soundcloud:search"),
            tracks=self.backend.remote.search(search_query),
        )

    @override
    def lookup(self, uri: Uri) -> list[Track]:
        if uri.startswith("sc:"):
            uri = Uri(uri.removeprefix("sc:"))
            return list(self.backend.remote.resolve_url(uri))

        try:
            track_id = self.backend.remote.parse_track_uri(uri)
            track = self.backend.remote.get_track(track_id)
            if track is None:
                logger.info(f"Failed to lookup {uri}: SoundCloud track not found")
                return []
        except Exception as error:  # noqa: BLE001
            logger.error(f"Failed to lookup {uri}: {error}")  # noqa: TRY400
            return []
        else:
            return [track]
