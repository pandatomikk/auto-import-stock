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
