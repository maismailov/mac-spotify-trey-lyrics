#!/usr/bin/env python3
import rumps
import requests
import re
import time
from Foundation import NSDistributedNotificationCenter

class SpotifyLyrics(rumps.App):
    def __init__(self):
        super(SpotifyLyrics, self).__init__("♪", quit_button=None)
        self.menu = ["No track playing"]
        
        self.current_track_id = None
        self.current_track_name = None
        self.current_artist = None
        self.lyrics_data = []
        self.playback_position_ms = 0
        self.last_update_time = 0.0
        self.is_playing = False
        self.last_lyric_line = ""
        self.current_line_start_ms = 0
        self.current_line_chunks = []
        
        self.sync_timer = rumps.Timer(self.sync_lyrics, 0.1)
        self.sync_timer.start()
        
        notification_center = NSDistributedNotificationCenter.defaultCenter()
        notification_center.addObserver_selector_name_object_(
            self,
            "playbackStateChanged:",
            "com.spotify.client.PlaybackStateChanged",
            None
        )
    
    def playbackStateChanged_(self, notification):
        user_info = notification.userInfo()
        if not user_info:
            return
        
        track_id = user_info.get("Track ID", "")
        player_state = user_info.get("Player State", "Stopped")
        playback_position_secs = float(user_info.get("Playback Position", 0))
        
        self.current_track_name = user_info.get("Name", "")
        self.current_artist = user_info.get("Artist", "")
        self.is_playing = player_state == "Playing"
        self.playback_position_ms = int(playback_position_secs * 1000)
        self.last_update_time = time.time()
        
        if not self.is_playing:
            self.title = "⏸"
            self.menu.clear()
            self.menu = ["Paused"]
            return
        
        if track_id and track_id != self.current_track_id:
            self.current_track_id = track_id
            self.fetch_lyrics(track_id)
    
    def fetch_lyrics(self, track_id):
        self.lyrics_data = []
        self.last_lyric_line = ""
        
        if not self.current_track_name or not self.current_artist:
            return
        
        try:
            url = "https://lrclib.net/api/get"
            params = {
                "artist_name": self.current_artist,
                "track_name": self.current_track_name
            }
            
            response = requests.get(url, params=params, timeout=4)
            
            if response.status_code == 200:
                data = response.json()
                synced_lyrics = data.get("syncedLyrics", "")
                
                if synced_lyrics:
                    for line in synced_lyrics.strip().split('\n'):
                        match = re.match(r'\[(\d+):(\d+\.\d+)\](.*)', line)
                        if match:
                            minutes = int(match.group(1))
                            seconds = float(match.group(2))
                            text = match.group(3).strip()
                            
                            if text:
                                self.lyrics_data.append({
                                    "startTimeMs": int((minutes * 60 + seconds) * 1000),
                                    "words": text
                                })
                    
                    if self.lyrics_data:
                        return
            
            self.title = "No lyrics"
            self.menu.clear()
            self.menu = ["No lyrics available"]
                
        except:
            self.title = "♪"
            self.menu.clear()
            self.menu = ["Failed to fetch lyrics"]
    
    def split_into_chunks(self, text):
        HANGING_WORDS = {'в', 'на', 'с', 'у', 'к', 'о', 'и', 'а', 'но', 'за', 'из', 'от', 'по', 
                        'by', 'on', 'at', 'in', 'with', 'a', 'the', 'and', 'for', 'of', 'to'}
        
        chunks = []
        parts = re.split(r'(\([^)]*\)|\[[^\]]*\]|"[^"]*"|«[^»]*»)', text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            is_structural = part.startswith(('(', '[', '"', '«'))
            
            if is_structural:
                chunks.append(part)
            else:
                words = part.split()
                
                if len(words) <= 4:
                    chunks.append(part)
                elif len(words) <= 6 and len(part) <= 30:
                    chunks.append(part)
                else:
                    i = 0
                    while i < len(words):
                        remaining = len(words) - i
                        
                        if remaining <= 2:
                            if chunks:
                                chunks[-1] += " " + " ".join(words[i:])
                            else:
                                chunks.append(" ".join(words[i:]))
                            break
                        
                        if remaining <= 6:
                            chunk_size = remaining
                        else:
                            chunk_size = 4
                            
                            if chunk_size < remaining and words[i + chunk_size - 1].lower() in HANGING_WORDS:
                                chunk_size = 3
                        
                        chunk_words = words[i:i+chunk_size]
                        chunk_text = " ".join(chunk_words)
                        chunk_text = re.sub(r'[,\-:;]+$', '', chunk_text)
                        
                        if i + chunk_size < len(words):
                            remaining_after = len(words) - (i + chunk_size)
                            if remaining_after > 2:
                                chunk_text += "..."
                        
                        chunks.append(chunk_text)
                        i += chunk_size
        
        return chunks
    
    def sync_lyrics(self, _):
        if not self.is_playing or not self.lyrics_data:
            return
        
        elapsed_ms = int((time.time() - self.last_update_time) * 1000)
        current_ms = self.playback_position_ms + elapsed_ms
        
        current_line = None
        next_line_start_ms = None
        
        for i, line in enumerate(self.lyrics_data):
            if current_ms >= line.get("startTimeMs", 0):
                current_line = line
                if i + 1 < len(self.lyrics_data):
                    next_line_start_ms = self.lyrics_data[i + 1].get("startTimeMs", 0)
            else:
                break
        
        if current_line:
            full_text = current_line.get("words", "♪")
            line_start_ms = current_line.get("startTimeMs", 0)
            
            if full_text != self.last_lyric_line:
                self.last_lyric_line = full_text
                self.current_line_start_ms = line_start_ms
                self.current_line_chunks = self.split_into_chunks(full_text)
                print(full_text)
                
                self.menu.clear()
                full_item = rumps.MenuItem(full_text)
                full_item.set_callback(None)
                self.menu = [full_item]
            
            if self.current_line_chunks and next_line_start_ms:
                line_duration_ms = next_line_start_ms - line_start_ms
                elapsed_in_line_ms = current_ms - line_start_ms
                
                num_chunks = len(self.current_line_chunks)
                ms_per_chunk = line_duration_ms / num_chunks if num_chunks > 0 else 0
                
                current_chunk = int(elapsed_in_line_ms / ms_per_chunk) if ms_per_chunk > 0 else 0
                current_chunk = min(current_chunk, num_chunks - 1)
                
                self.title = self.current_line_chunks[current_chunk]
            else:
                if self.current_line_chunks:
                    self.title = self.current_line_chunks[0]
                else:
                    self.title = full_text[:40]

if __name__ == "__main__":
    SpotifyLyrics().run()