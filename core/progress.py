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
    """Sequential photo ETA; measure image work only, excluding catalogue lookups."""
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
