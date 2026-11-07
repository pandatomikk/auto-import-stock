from collections import deque
class ImageProgress:
    def __init__(self,total,workers):
        self.total=total;self.workers=workers;self.done=0
        self.counts={'downloaded':0,'existing':0,'failed':0};self.samples=deque(maxlen=20)
    def update(self,record):
        self.done+=1
        status=record['status'];self.counts[status if status in self.counts else 'failed']+=1
        if status=='downloaded' and record.get('duration',0)>0:self.samples.append(record['duration'])
        remaining=max(0,self.total-self.done)
        eta=0 if not remaining else (sum(self.samples)/len(self.samples)*remaining/min(self.workers,remaining) if self.samples else None)
        return dict(total=self.total,done=self.done,eta=eta,**self.counts)


def preparation_event(stage, message, done=None, total=None):
    """Structured, flushed events consumed by the desktop client and CLI logs."""
    import json
    print('ZPSI_PREPARATION ' + json.dumps({'stage': stage, 'message': message, 'done': done, 'total': total}, ensure_ascii=False), flush=True)


class ConversionProgress:
    """Estimate a sequential phase from completed operations."""
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.converted = 0
        self.cached = 0
        self.seconds = 0.0
        self.average = None

    def update(self, duration, cached=False):
        self.done += 1
        if cached:
            self.cached += 1
        else:
            self.converted += 1
            self.seconds += max(0.0, duration)
        if self.converted and (self.average is None or self.done % 10 == 0 or self.done == self.total):
            self.average = self.seconds / self.converted
        return self.snapshot()

    def snapshot(self):
        remaining = max(0, self.total - self.done)
        eta = 0 if not remaining else (None if self.average is None else self.average * remaining)
        return dict(done=self.done, total=self.total, eta=eta,
                    converted=self.converted, cached=self.cached)

    def emit(self):
        import json
        print('ZPSI_LOCAL_IMAGES ' + json.dumps(self.snapshot()), flush=True)


def format_image_eta(seconds):
    if seconds is None:
        return 'Temps restant pour les images : estimation après la première conversion…'
    if seconds <= 0:
        return 'Conversion des images terminée.'
    import math
    seconds = math.ceil(seconds)
    if seconds < 60:
        duration = f'{seconds} s'
    elif seconds < 3600:
        duration = f'{seconds // 60} min {seconds % 60:02d} s'
    else:
        duration = f'{seconds // 3600} h {(seconds % 3600) // 60:02d} min'
    return 'Temps restant pour les images : environ ' + duration


def publication_status(label, tracker, current='', *, on_status=None):
    event = tracker.snapshot()
    if on_status is not None:
        on_status(event)
    seconds = event['eta']
    if seconds is None:
        estimate = 'estimation après la première opération…'
    elif seconds == 0:
        estimate = 'étape terminée'
    else:
        estimate = format_image_eta(seconds).replace('Temps restant pour les images : ', 'temps restant : ')
    return f"{label} : {event['done']}/{event['total']} · {estimate}" + (' · ' + current if current else '')


class DriveSearchProgress:
    """Estimate search time from unique covered products across all sources."""
    def __init__(self, total, clock=None):
        import time
        self.clock = clock or time.monotonic
        self.started = self.clock()
        self.total = total
        self.found = set()
        self.average = None
        self.checkpoint = 0

    def update(self, references):
        self.found.update(references)
        done = len(self.found)
        if done and (self.average is None or done >= self.checkpoint + 10):
            self.average = max(0, self.clock() - self.started) / done
            self.checkpoint = done
        return self.snapshot()

    def snapshot(self, finished=False):
        done = len(self.found)
        remaining = max(0, self.total - done)
        eta = self.average * remaining if self.average is not None and remaining else None
        return dict(done=done, total=self.total, eta=eta, finished=finished)

    def emit(self, references=(), finished=False):
        import json
        self.update(references)
        print('ZPSI_DRIVE_SEARCH ' + json.dumps(self.snapshot(finished)), flush=True)


def format_drive_eta(event):
    if event.get('finished'):
        return 'Recherche terminée : ' + str(event['total'] - event['done']) + ' produit(s) sans correspondance photo.'
    if event['done'] >= event['total']:
        return 'Produits trouvés ; vérification des dossiers et sources restantes…'
    if event.get('eta') is None:
        return 'Temps restant estimé : calcul après le premier produit trouvé…'
    if event['eta'] <= 0:
        return 'Recherche Drive — temps restant estimé : moins de 1 s (approximatif)'
    duration = format_image_eta(event['eta']).replace('Temps restant pour les images : ', '')
    return 'Recherche Drive — temps restant estimé : ' + duration + ' (approximatif)'
