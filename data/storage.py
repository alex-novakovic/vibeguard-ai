from data.schemas import VisionDoc, FeatureLogItem, SessionEntry, CycleItem, DriftItem
from data.state import ProjectState
from interfaces import StorageBackend
from typing import List, Optional
from utils.common import now, now_dt
import uuid

from utils.exceptions import (
    DatabaseError,
    EventError,
    MissingFeatureId,
    MissingSessionId
)

class Storage(StorageBackend):

    async def initialize_feature_log(self, vision_doc: VisionDoc) -> list:
        
        feature_log = []
        
        for feature in vision_doc.backlog:
            # Kreiramo Beanie dokument za svaki item iz backloga
            log_item = FeatureLogItem(
                user_id=vision_doc.user_id,
                feature_id=feature.id,
                name=feature.name,
                status="to_do",
                cycles=[],
                drift_events=[]
            )
            

            # DIREKTNO UPISIVANJE U BAZU:
            # Pošto je operacija asinhrona, moramo staviti 'await'
            #await log_item.insert()
            
            # Dodajemo upisani dokument u našu listu
            feature_log.append(log_item)
            
        return feature_log

    async def load_or_create_project(self, user_id: str) -> tuple:   
        try:
            # 1. Tražimo VisionDoc za korisnika
            vision_doc = await VisionDoc.find_one(VisionDoc.user_id == user_id)
            # Ako korisnik ne postoji u bazi, vraćamo čist nov stanje
            if vision_doc is None:
                return "new", ProjectState()

            if vision_doc:
               # 2. Ako postoji, povlačimo sve njegove feature logove iz MongoDB-u  
               feature_log = await FeatureLogItem.find(FeatureLogItem.user_id == user_id).to_list()
            
               # 3. Povlačimo sve njegove dosadašnje sesije
               session_log = await SessionEntry.find(SessionEntry.user_id == user_id).to_list() 
                # 4. Pakujemo sve u ProjectState (dodatna polja se sama inicijalizuju unutar klase)
               state = ProjectState(
                    vision_doc=vision_doc, 
                    feature_log=feature_log, 
                    session_log=session_log
                )
               return "existing", state

        except Exception as e:
          raise DatabaseError(f"Project could not be loaded from database: {e}") from e

    async def log_feature_cycle(self, feature_log: list, user_id: str, feature_id: str, event: str, vision_doc: VisionDoc, alignment_note: str = None, drift_event: str = None) -> list:

        if event not in ("start", "complete", "in_progress"):
            raise EventError(f"Invalid event: {event}. Must be 'start', 'complete' or 'in_progress'")
        
        try:
           item = next(
             (i for i in feature_log 
              if i.user_id == user_id and i.feature_id == feature_id)
        )
        except Exception as e:
            raise MissingFeatureId(f"Feature '{feature_id}' not found for user {user_id}.")

        timestamp = now()

        # 2. Menjamo podatke unutar tog dokumenta (sada preko čistih Pydantic modela)
        if event == "start":
            item.status = "in_progress"
            item.cycles.append(
                CycleItem(started_at=timestamp, completed_at=None, alignment_notes=[])
            )
            if drift_event:
                item.drift_events.append(
                    DriftItem(drift_time=timestamp, drift_note=drift_event)
                )

        elif event == "in_progress":
            if not item.cycles:
                raise EventError(f"Cannot update '{feature_id}': no active cycle. Call log_feature_cycle with event='start' first.")
            if alignment_note is not None:
                item.cycles[-1].alignment_notes.append(
                    {"timestamp": timestamp, "note": alignment_note}
                )
            if drift_event is not None:
                item.drift_events.append(
                    DriftItem(drift_time=timestamp, drift_note=drift_event)
                )

        elif event == "complete":
            if not item.cycles:
                raise EventError(f"Cannot complete '{feature_id}': no active cycle.")
            item.status = "complete"
            item.cycles[-1].completed_at = timestamp
            if alignment_note is not None:
               item.cycles[-1].alignment_notes.append({
                    "timestamp": timestamp,
                    "note": alignment_note
        })
  
        if vision_doc is not None and event in ("start", "complete"):
            new_status = "in_progress" if event == "start" else "complete"
            for backlog_item in vision_doc.backlog:
                if backlog_item.id == feature_id:
                    backlog_item.status = new_status
                    break

        return feature_log
    
    async def start_session(self, user_id: str) -> SessionEntry:
        new_session = SessionEntry(
            user_id=user_id,
            workSessionId=str(uuid.uuid4()),
            startTime=now_dt()
        )
        await new_session.insert()
        return new_session

    async def end_session(self, user_id: str, session_id: str, total_tokens: int) -> SessionEntry:
        try:
            session = await SessionEntry.find_one(
                SessionEntry.user_id == user_id, 
                SessionEntry.workSessionId == session_id
            )
        except Exception as e:
            raise DatabaseError(f"Failed to fetch session from database: {e}") from e
        
        if session is None:
            raise MissingSessionId(f"Session {session_id} not found")
        
        # TODO: vratiti da se prima feature_log iz state-a
        try: # Agregacija podataka direktno iz FeatureLogItem kolekcije u bazi
            features = await FeatureLogItem.find(FeatureLogItem.user_id == user_id).to_list()
        except Exception as e:
            raise DatabaseError(f"Failed to fetch feature logs from database: {e}") from e
        
        completed = [f.feature_id for f in features if f.status == "complete"]
        drift_count = sum(len(f.drift_events) for f in features)
        
        start = session.startTime
        end = now_dt()
        duration = int((end - start).total_seconds() / 60)
        session.endTime = end
        session.featureCyclesCompleted = completed
        session.driftEventsCount = drift_count
        session.totalTokensUsed = total_tokens
        session.totalDurationMinutes = duration
        
        #try:
         #   await session.save()
        #xcept Exception as e:
         #   raise DatabaseError(f"Failed to save session to database: {e}") from e
        return session

    async def dump_logs(self, vision_doc: Optional[VisionDoc], feature_log: List[FeatureLogItem], session_log: List[SessionEntry]) -> None:
        """
        Zamenjuje staro upisivanje u lokalne fajlove na disku.
        Sada direktno i asinhrono čuva prosleđene Beanie dokumente u MongoDB.
        """
        try:
            # 1. Ako postoji vizija, asinhrono je čuvamo/ažuriramo u bazi
            if vision_doc:
                await vision_doc.save()

            # 2. Prolazimo kroz listu feature logova i ažuriramo svaki u bazi
            if feature_log is not None:
                for feature in feature_log:
                    await feature.save()

            # 3. Prolazimo kroz listu sesija i ažuriramo svaku u bazi
            if session_log is not None:
                for session_entry in session_log:
                    await session_entry.save()


        except Exception as e:
            # Umesto FileSystemError, sada bacamo VibeGuardError ako pukne baza
            raise DatabaseError(f"Database save failed during dump_logs: {e}") from e

