import itertools
from rasa.core.tracker_store import (TrackerStore)
from rasa.shared.core.domain import Domain
from typing import (Optional, Text, Dict, Any, List, Iterable,
                    Iterator, Union)
from rasa.core.brokers.broker import EventBroker

from rasa.shared.core.events import SessionStarted

from rasa.shared.core.trackers import (
    ActionExecuted,
    DialogueStateTracker,
    EventVerbosity,
)


class MongoTrackerStore(TrackerStore):
    """
    Stores conversation history in Mongo
    Property methods:
        conversations: returns the current conversation
    """

    def __init__(
        self,
        domain: Domain,
        host: Optional[Text] = "mongodb://localhost:27017",
        db: Optional[Text] = "rasa",
        username: Optional[Text] = None,
        password: Optional[Text] = None,
        auth_source: Optional[Text] = "admin",
        collection: Optional[Text] = "conversations",
        event_broker: Optional[EventBroker] = None,
        **kwargs: Dict[Text, Any],
    ) -> None:
        from pymongo.database import Database
        from pymongo import MongoClient

        self.client = MongoClient(
            host,
            username=username,
            password=password,
            authSource=auth_source,
            # delay connect until process forking is done
            connect=False,
        )

        self.db = Database(self.client, db)
        self.collection = collection
        super().__init__(domain, event_broker, **kwargs)

        self._ensure_indices()

    @property
    def conversations(self):
        """Returns the current conversation"""
        return self.db[self.collection]

    def _ensure_indices(self):
        """Create an index on the sender_id"""
        self.conversations.create_index("sender_id")

    @staticmethod
    def _current_tracker_state_without_events(tracker: DialogueStateTracker) -> Dict:
        # get current tracker state and remove `events` key from state
        # since events are pushed separately in the `update_one()` operation
        state = tracker.current_state(EventVerbosity.ALL)
        state.pop("events", None)

        return state

    def save(self, tracker, timeout=None):
        """Saves the current conversation state"""
        if self.event_broker:
            self.stream_events(tracker)

        additional_events = self._additional_events(tracker)

        self.conversations.update_one(
            {"sender_id": tracker.sender_id},
            {
                "$set": self._current_tracker_state_without_events(tracker),
                "$push": {
                    "events": {"$each": [e.as_dict() for e in additional_events]}
                },
            },
            upsert=True,
        )

    def _additional_events(self, tracker: DialogueStateTracker) -> Iterator:
        """Return events from the tracker which aren't currently stored.
        Args:
            tracker: Tracker to inspect.
        Returns:
            List of serialised events that aren't currently stored.
        """

        stored = self.conversations.find_one(
            {"sender_id": tracker.sender_id}) or {}
        all_events = self._events_from_serialized_tracker(stored)
        number_events_since_last_session = len(
            self._events_since_last_session_start(all_events)
        )

        return itertools.islice(
            tracker.events, number_events_since_last_session, len(
                tracker.events)
        )

    @staticmethod
    def _events_from_serialized_tracker(serialised: Dict) -> List[Dict]:
        return serialised.get("events", [])

    @staticmethod
    def _events_since_last_session_start(events: List[Dict]) -> List[Dict]:
        """Retrieve events since and including the latest `SessionStart` event.
        Args:
            events: All events for a conversation ID.
        Returns:
            List of serialised events since and including the latest `SessionStarted`
            event. Returns all events if no such event is found.
        """

        events_after_session_start = []
        for event in reversed(events):
            events_after_session_start.append(event)
            if event["event"] == SessionStarted.type_name:
                break

        return list(reversed(events_after_session_start))

    def _retrieve(
        self, sender_id: Text, fetch_events_from_all_sessions: bool
    ) -> Optional[List[Dict[Text, Any]]]:
        stored = self.conversations.find_one({"sender_id": sender_id})

        # look for conversations which have used an `int` sender_id in the past
        # and update them.
        if not stored and sender_id.isdigit():
            from pymongo import ReturnDocument

            stored = self.conversations.find_one_and_update(
                {"sender_id": int(sender_id)},
                {"$set": {"sender_id": str(sender_id)}},
                return_document=ReturnDocument.AFTER,
            )

        if not stored:
            return None

        events = self._events_from_serialized_tracker(stored)

        if not fetch_events_from_all_sessions:
            events = self._events_since_last_session_start(events)

        return events

    def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        # TODO: Remove this in Rasa Open Source 3.0 along with the
        # deprecation warning in the constructor
        if self.retrieve_events_from_previous_conversation_sessions:
            return self.retrieve_full_tracker(sender_id)

        events = self._retrieve(
            sender_id, fetch_events_from_all_sessions=False)

        if not events:
            return None

        return DialogueStateTracker.from_dict(sender_id, events, self.domain.slots)

    def retrieve_full_tracker(
        self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        events = self._retrieve(
            conversation_id, fetch_events_from_all_sessions=True)

        if not events:
            return None

        return DialogueStateTracker.from_dict(
            conversation_id, events, self.domain.slots
        )

    def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Mongo Tracker Store"""
        return [c["sender_id"] for c in self.conversations.find()]


def _create_sequence(table_name: Text) -> "Sequence":
    pass


def is_postgresql_url(url: Union[Text, "URL"]) -> bool:
    pass


def create_engine_kwargs(url: Union[Text, "URL"]) -> Dict[Text, Any]:
    pass


def ensure_schema_exists(session: "Session") -> None:
    pass

# class MongoAsyncTrackerStore(TrackerStore):
#     """
#     Stores conversation history in Mongo
#     Property methods:
#         conversations: returns the current conversation
#     """

#     def __init__(
#         self,
#         domain: Domain,
#         host: Optional[Text] = "mongodb://localhost:27017",
#         db: Optional[Text] = "rasa",
#         username: Optional[Text] = None,
#         password: Optional[Text] = None,
#         auth_source: Optional[Text] = "admin",
#         collection: Optional[Text] = "conversations",
#         event_broker: Optional[EventBroker] = None,
#         **kwargs: Dict[Text, Any],
#     ) -> None:
#         # from pymongo.database import Database
#         # from pymongo import MongoClient
#         from motor.motor_asyncio import (
#             AsyncIOMotorClient, AsyncIOMotorDatabase)

#         self.client = AsyncIOMotorClient(
#             f"mongodb+srv://motiapp:{password}@moti1.piqgh.mongodb.net/{db}?retryWrites=true&w=majority"
#             # username=username,
#             # password=password,
#             # authSource=auth_source,
#             # # delay connect until process forking is done
#             # connect=False,
#         )

#         self.db = AsyncIOMotorDatabase(self.client, db)
#         self.collection = collection
#         super().__init__(domain, event_broker, **kwargs)

#     @property
#     def conversations(self):
#         """Returns the current conversation"""
#         return self.db[self.collection]

#     async def _ensure_indices(self):
#         """Create an index on the sender_id"""
#         await self.conversations.create_index("sender_id")

#     @staticmethod
#     def _current_tracker_state_without_events(tracker: DialogueStateTracker) -> Dict:
#         # get current tracker state and remove `events` key from state
#         # since events are pushed separately in the `update_one()` operation
#         state = tracker.current_state(EventVerbosity.ALL)
#         state.pop("events", None)

#         return state

#     async def save(self, tracker, timeout=None):
#         """Saves the current conversation state"""
#         if self.event_broker:
#             self.stream_events(tracker)

#         additional_events = await self._additional_events(tracker)

#         await self.conversations.update_one(
#             {"sender_id": tracker.sender_id},
#             {
#                 "$set": self._current_tracker_state_without_events(tracker),
#                 "$push": {
#                     "events": {"$each": [e.as_dict() for e in additional_events]}
#                 },
#             },
#             upsert=True,
#         )

#     async def _additional_events(self, tracker: DialogueStateTracker) -> Iterator:
#         """Return events from the tracker which aren't currently stored.
#         Args:
#             tracker: Tracker to inspect.
#         Returns:
#             List of serialised events that aren't currently stored.
#         """

#         stored = await self.conversations.find_one(
#             {"sender_id": tracker.sender_id}) or {}
#         all_events = self._events_from_serialized_tracker(stored)
#         number_events_since_last_session = len(
#             self._events_since_last_session_start(all_events)
#         )

#         return itertools.islice(
#             tracker.events, number_events_since_last_session, len(
#                 tracker.events)
#         )

#     @staticmethod
#     def _events_from_serialized_tracker(serialised: Dict) -> List[Dict]:
#         return serialised.get("events", [])

#     @staticmethod
#     def _events_since_last_session_start(events: List[Dict]) -> List[Dict]:
#         """Retrieve events since and including the latest `SessionStart` event.
#         Args:
#             events: All events for a conversation ID.
#         Returns:
#             List of serialised events since and including the latest `SessionStarted`
#             event. Returns all events if no such event is found.
#         """

#         events_after_session_start = []
#         for event in reversed(events):
#             events_after_session_start.append(event)
#             if event["event"] == SessionStarted.type_name:
#                 break

#         return list(reversed(events_after_session_start))

#     async def _retrieve(
#         self, sender_id: Text, fetch_events_from_all_sessions: bool
#     ) -> Optional[List[Dict[Text, Any]]]:
#         stored = await self.conversations.find_one({"sender_id": sender_id})

#         # look for conversations which have used an `int` sender_id in the past
#         # and update them.
#         if not stored and sender_id.isdigit():
#             from pymongo import ReturnDocument

#             stored = await self.conversations.find_one_and_update(
#                 {"sender_id": int(sender_id)},
#                 {"$set": {"sender_id": str(sender_id)}},
#                 return_document=ReturnDocument.AFTER,
#             )

#         if not stored:
#             return None

#         events = self._events_from_serialized_tracker(stored)

#         if not fetch_events_from_all_sessions:
#             events = self._events_since_last_session_start(events)

#         return events

#     async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
#         # TODO: Remove this in Rasa Open Source 3.0 along with the
#         # deprecation warning in the constructor
#         if self.retrieve_events_from_previous_conversation_sessions:
#             return await self.retrieve_full_tracker(sender_id)

#         events = await self._retrieve(
#             sender_id, fetch_events_from_all_sessions=False)

#         if not events:
#             return None

#         return DialogueStateTracker.from_dict(sender_id, events, self.domain.slots)

#     async def retrieve_full_tracker(
#         self, conversation_id: Text
#     ) -> Optional[DialogueStateTracker]:
#         events = await self._retrieve(
#             conversation_id, fetch_events_from_all_sessions=True)

#         if not events:
#             return None

#         return DialogueStateTracker.from_dict(
#             conversation_id, events, self.domain.slots
#         )

#     async def keys(self) -> Iterable[Text]:
#         """Returns sender_ids of the Mongo Tracker Store"""
#         return [c["sender_id"] async for c in await self.conversations.find()]
