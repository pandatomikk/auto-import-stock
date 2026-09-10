"""Client de bureau : le moteur tourne dans un processus séparé."""
import json,os,queue,re,signal,subprocess,sys,threading,time
from pathlib import Path
from core.profiles import discover_profiles, read_profile, workflow_kind
import tkinter as tk
from tkinter import ttk,messagebox
from core import file_picker as filedialog
ROOT=Path(__file__).resolve().parent
# Only the installed client augments its own process environment.
if os.name=='nt' and (ROOT/'runtime_windows.json').is_file():
 runtime=json.loads((ROOT/'runtime_windows.json').read_text(encoding='utf-8'))
 os.environ['PATH']=os.pathsep.join(runtime['paths'])+os.pathsep+os.environ.get('PATH','')
 os.environ['TESSDATA_PREFIX']=runtime['tessdata']

class Client(tk.Tk):
 def __init__(self):
  super().__init__();self.title('Import fournisseurs — ZPSI · V0.20');self.geometry('960x720');self.minsize(820,680);self.configure(bg='#f4f1f7')
  from core.shop_connection import initialize_storage
  from core.profiles import private_directory
  initialize_storage()
  for name in ('profiles','rules','adapters'):(private_directory()/name).mkdir(parents=True,exist_ok=True)
  self.configs={p.stem:read_profile(p) for p in discover_profiles()}
  default=next((key for key,value in self.configs.items() if value.get('default')),next(iter(self.configs),''))
  self.image_values={}
  self.previous_brand=default
  self.proc=None;self.events=queue.Queue();self.stopped=False;self.folder=None
  self.diagnostic=None
  self.resume_path=None;self.workflow_result=None;self.failure_detail=None
  style=ttk.Style(self);style.theme_use('clam')
  style.configure('.',font=('Arial',11),background='white',foreground='#302438')
  style.configure('TFrame',background='white');style.configure('TLabel',background='white')
  style.configure('TButton',padding=(16,10),background='#eee8f3',borderwidth=0)
  style.map('TButton',background=[('active','#e2d5eb')])
  style.configure('Primary.TButton',background='#59216a',foreground='white',font=('Arial',11,'bold'))
  style.map('Primary.TButton',background=[('active','#713884'),('disabled','#c9b9d0')],foreground=[('disabled','#f6f3f8')])
  style.configure('TEntry',padding=10,fieldbackground='#f8f6fa',bordercolor='#e2dce8')
  style.configure('TCombobox',padding=9,fieldbackground='#f8f6fa')
  style.configure('TCheckbutton',padding=6,background='white')
  style.configure('Horizontal.TProgressbar',background='#80509a',troughcolor='#eee8f3',borderwidth=0)
  header=tk.Frame(self,bg='#3c1648',height=120);header.pack(fill='x');header.pack_propagate(False)
  ttk.Button(header,text='Ma boutique',command=self.open_shop).pack(side='right',padx=24)
  tk.Label(header,text='ZPSI  /  CATALOGUE',bg='#3c1648',fg='#f4c95d',font=('Arial',10,'bold')).pack(anchor='w',padx=32,pady=(18,5))
  tk.Label(header,text='Vos produits, prêts pour la boutique.',bg='#3c1648',fg='white',font=('Arial',23,'bold')).pack(anchor='w',padx=32)
  tk.Label(header,text='Une facture, des images. On prépare le reste.',bg='#3c1648',fg='#ddcde5',font=('Arial',11)).pack(anchor='w',padx=32,pady=5)
  box=ttk.Frame(self,padding=26);box.pack(fill='both',expand=True,padx=24,pady=22);box.columnconfigure(1,weight=1)
  self.rules_button=ttk.Button(box,text='Règles produits…',command=self.open_product_rules);self.rules_button.grid(row=0,column=2,sticky='e')
  ttk.Label(box,text='Votre sélection',font=('Arial',15,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,16))
  self.brand=tk.StringVar(value=default);self.source=tk.StringVar();self.drive=tk.StringVar();self.zip=tk.StringVar();self.base=tk.StringVar();self.test=tk.BooleanVar(value=True);self.web=tk.BooleanVar(value=True)
  ttk.Label(box,text='Marque').grid(row=1,column=0,sticky='w');self.select=ttk.Combobox(box,textvariable=self.brand,values=list(self.configs),state='readonly');self.select.grid(row=1,column=1,sticky='ew');self.select.bind('<<ComboboxSelected>>',self.brand_changed)
  self.inputs=[self.select,self.rules_button]
  self.field(box,2,'Facture / catalogue',self.source,lambda:self.pick(self.source))
  self.image_label=ttk.Label(box,text='Images');self.image_label.grid(row=3,column=0,sticky='w')
  self.image_entry=ttk.Entry(box,textvariable=self.drive);self.image_entry.grid(row=3,column=1,sticky='ew');self.inputs.append(self.image_entry)
  self.image_browse=ttk.Button(box,text='Parcourir…',command=lambda:self.pick(self.drive));self.image_browse.grid(row=3,column=2,padx=6);self.inputs.append(self.image_browse)
  self.two_pass_tools=ttk.Frame(box);self.two_pass_tools.grid(row=4,column=0,columnspan=3,sticky='w',pady=8)
  self.resume_button=ttk.Button(self.two_pass_tools,text='Reprendre une préparation…',command=self.pick_session);self.resume_button.pack(side='left');self.inputs.append(self.resume_button)
  self.ean_button=ttk.Button(self.two_pass_tools,text='Ouvrir la liste EAN',command=self.open_eans);self.ean_button.pack(side='left',padx=8);self.inputs.append(self.ean_button)
  self.test_widget=ttk.Checkbutton(box,text='Commencer avec 5 images pour essayer',variable=self.test);self.test_widget.grid(row=6,column=1,sticky='w');self.inputs.append(self.test_widget)
  w=ttk.Checkbutton(box,text='Récupérer les descriptions fournisseur',variable=self.web);w.grid(row=7,column=1,sticky='w');self.inputs.append(w);self.web_widget=w
  actions=ttk.Frame(box);actions.grid(row=8,column=0,columnspan=3,sticky='ew',pady=12)
  self.start_button=ttk.Button(actions,text='Préparer mes produits',style='Primary.TButton',command=self.start);self.start_button.pack(side='left')
  self.stop_button=ttk.Button(actions,text='Arrêter',command=self.stop,state='disabled');self.stop_button.pack(side='left',padx=8)
  self.log_button=ttk.Button(actions,text='Voir le journal',command=self.open_diagnostic,state='disabled');self.log_button.pack(side='left',padx=8)
  self.open_button=ttk.Button(actions,text='Voir mes fichiers',command=self.open_folder,state='disabled');self.open_button.pack(side='right')
  progress=ttk.Frame(box);progress.grid(row=9,column=0,columnspan=3,sticky='ew')
  self.stage=tk.StringVar(value='1  Lecture de la facture    ·    2  Images    ·    3  Descriptions    ·    4  Fichiers prêts')
  ttk.Label(progress,textvariable=self.stage,foreground='#80509a',font=('Arial',10,'bold')).pack(anchor='w',pady=(8,14))
  self.status=tk.StringVar(value='Tout est prêt pour commencer.');ttk.Label(progress,textvariable=self.status,wraplength=800).pack(anchor='w')
  self.bar=ttk.Progressbar(progress,mode='determinate');self.bar.pack(fill='x',pady=8)
  self.eta=tk.StringVar(value='');ttk.Label(progress,textvariable=self.eta).pack(anchor='w')
  self.activity=tk.StringVar(value='');ttk.Label(progress,textvariable=self.activity,foreground='#84768a',font=('Arial',10)).pack(anchor='w',pady=(4,0))
  ttk.Label(box,text='Vos fichiers restent sur cet ordinateur. Vous choisissez quand les importer dans la boutique.',foreground='#84768a',wraplength=800,font=('Arial',10)).grid(row=10,column=0,columnspan=3,sticky='w',pady=(22,0))
  self.source.trace_add('write',self.selection_changed)
  self.protocol('WM_DELETE_WINDOW',self.close);self.brand_changed();self.poll_timer=self.after(150,self.poll)
 def open_product_rules(self):
  if self.proc:return
  from core.product_rules import rules_path
  from core.product_rules_ui import ProductRulesDialog
  source=Path(self.source.get()).expanduser()
  if source.suffix.lower()=='.json':
   from core.media_workflow import load_session
   try:source=Path(load_session(source)['source'])
   except (OSError,ValueError):pass
  if not source.is_file():messagebox.showerror('Source','Sélectionnez le document fournisseur original.');return
  def saved():
   self.source.set(str(source));self.rebuild_preparation=self.is_two_pass();self.refresh_two_pass()
   self.status.set('Règles enregistrées. Relancez la préparation pour les appliquer ; la préparation précédente sera sauvegardée.')
  ProductRulesDialog(self,self.configs[self.brand.get()],source,rules_path(self.brand.get()),saved)
 def open_shop(self):
  from core.shop_ui import ShopDialog
  if getattr(self,'shop_dialog',None) is not None and self.shop_dialog.winfo_exists():
   self.shop_dialog.lift();return
  self.shop_dialog=ShopDialog(self)
 def field(self,box,row,label,var,command=None):
  ttk.Label(box,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
  w=ttk.Entry(box,textvariable=var);w.grid(row=row,column=1,sticky='ew');self.inputs.append(w)
  if command:
   w=ttk.Button(box,text='Parcourir…',command=command);w.grid(row=row,column=2,padx=6);self.inputs.append(w)
 def pick(self,var):
  value=filedialog.askopenfilename(filetypes=[('Archive ZIP','*.zip'),('Tous les fichiers','*')] if var is self.drive else [('Tous les fichiers','*')])
  if value:var.set(value)
 def pick_session(self):
  value=filedialog.askopenfilename(title='Reprendre une préparation',filetypes=[('Préparation','*_session.json')])
  if value:
   from core.media_workflow import load_session
   try:load_session(value)
   except (OSError,ValueError) as exc:messagebox.showerror('Préparation',str(exc));return
   self.source.set(value)
 def selection_changed(self,*args):
  if not self.proc:self.refresh_two_pass(show_status=True)
 def is_two_pass(self):
  return workflow_kind(self.configs.get(self.brand.get(),{}))=='two_pass'
 def refresh_two_pass(self,show_status=False):
  self.resume_path=None
  if not self.is_two_pass():
   self.two_pass_tools.grid_remove();self.start_button.configure(text='Préparer mes produits');return
  from core.media_workflow import load_session,session_path_for
  self.two_pass_tools.grid()
  value=self.source.get().strip()
  if value:
   source=Path(value).expanduser()
   candidate=source if source.suffix.lower()=='.json' else session_path_for(source)
   try:
    data=load_session(candidate)
    if source.suffix.lower()=='.json' or (data['status']=='waiting_images' and data.get('source')==str(source.resolve())):
     self.resume_path=candidate.resolve()
   except (OSError,ValueError):pass
  if getattr(self,'rebuild_preparation',False):self.resume_path=None
  waiting=self.resume_path is not None
  self.start_button.configure(text='2 · Finaliser avec les images' if waiting else '1 · Préparer le CSV et les EAN')
  self.image_label.configure(text='ZIP des images' if waiting else 'Images à récupérer à l’étape 2')
  self.image_entry.configure(state='normal' if waiting else 'disabled')
  self.image_browse.configure(state='normal' if waiting else 'disabled')
  self.image_browse.grid()
  self.test_widget.configure(state='disabled');self.web_widget.configure(state='disabled')
  self.ean_button.configure(state='normal' if waiting else 'disabled')
  if waiting:
   self.folder=self.resume_path.parent;self.open_button.configure(state='normal')
  if show_status:
   self.stage.set('En pause · Récupération des images la plateforme fournisseur' if waiting else 'Préparation · Étape 1 sur 2')
   self.status.set('Le CSV et la liste EAN sont prêts. Ouvrez la liste EAN, utilisez-la sur la plateforme fournisseur, téléchargez les photos en ZIP, puis sélectionnez ce ZIP pour finaliser.' if waiting else 'Préparez le CSV et la liste EAN. Vous pourrez ensuite récupérer les photos sur la plateforme fournisseur et reprendre ici.')
 def open_eans(self):
  if not self.resume_path:return
  from core.media_workflow import load_session
  try:
   data=load_session(self.resume_path);self.open_path(self.resume_path.parent/data['ean_text'])
  except (OSError,ValueError) as exc:messagebox.showerror('Liste EAN',str(exc))
 def brand_changed(self,event=None,show_status=True):
  if event is not None:self.rebuild_preparation=False
  if event is not None:self.image_values[self.previous_brand]=self.drive.get()
  brand=self.brand.get()
  if not brand:
   self.start_button.configure(state='disabled');self.status.set('Aucun profil disponible. Installer un profil local.');return
  settings=self.configs[brand].get('images',{})
  if event is not None or not self.drive.get():self.drive.set(self.image_values.get(brand,settings.get('drive_url','')))
  self.previous_brand=brand
  is_drive=settings.get('mode')=='drive'
  self.image_label.configure(text='Dossier Google Drive' if is_drive else 'ZIP des images')
  if is_drive:self.image_browse.grid_remove()
  else:self.image_browse.grid()
  self.test_widget.configure(state='normal' if is_drive else 'disabled')
  no_images=settings.get('mode')=='none'
  if no_images:
   self.image_browse.grid_remove()
   self.image_label.configure(text='Images non configurées')
  self.web_widget.configure(state='disabled' if no_images else 'normal')
  self.image_entry.configure(state='normal');self.image_browse.configure(state='normal')
  self.refresh_two_pass(show_status=show_status)
 def start(self):
  if self.is_two_pass():self.refresh_two_pass()
  source=Path(self.source.get()).expanduser()
  if not source.is_file() and not self.resume_path:messagebox.showerror('Source','Sélectionne un fichier existant.');return
  if self.is_two_pass() and source.suffix.lower()=='.json' and not self.resume_path:
   messagebox.showerror('Préparation','Sélectionne une préparation valide (*_session.json).');return
  if self.resume_path and not Path(self.drive.get()).expanduser().is_file():
   messagebox.showerror('Images','Récupère les images sur la plateforme fournisseur, puis sélectionne leur ZIP pour finaliser.');return
  if workflow_kind(self.configs[self.brand.get()])=='invoice' and not self.drive.get().strip():messagebox.showerror('Drive','Renseigne le lien du dossier Drive.');return
  if self.configs[self.brand.get()].get('images',{}).get('mode')=='zip_by_sku' and not Path(self.drive.get()).is_file():messagebox.showerror('Images','Sélectionne le ZIP des images.');return
  self.folder=source.resolve().parent;self.stopped=False;self.eta.set('Temps restant : calcul en cours…')
  python_exe=str(Path(sys.executable).with_name('python.exe')) if os.name=='nt' and Path(sys.executable).name.lower()=='pythonw.exe' else sys.executable
  args=[python_exe,'-u',str(ROOT/'lancer.py'),'--supplier',self.brand.get(),'--source',str(source.resolve())]
  if self.resume_path:
   args=[python_exe,'-u',str(ROOT/'lancer.py'),'--resume-session',str(self.resume_path),'--images-zip',str(Path(self.drive.get()).expanduser().resolve())]
  elif workflow_kind(self.configs[self.brand.get()])=='invoice':args+=['--drive-url',self.drive.get().strip(),'--test-images' if self.test.get() else '--all-images']
  elif self.configs[self.brand.get()].get('images',{}).get('mode')=='zip_by_sku':args+=['--images-zip',self.drive.get()]
  from core.product_rules import rules_path
  args+=['--product-rules',str(rules_path(self.brand.get()))]
  if getattr(self,'rebuild_preparation',False) and not self.resume_path:args+=['--rebuild-preparation']
  if self.is_two_pass() or not self.web.get() or self.configs[self.brand.get()].get('images',{}).get('mode')=='none':args+=['--no-web-descriptions']
  self.workflow_result=None;self.failure_detail=None
  try:
   self.diagnostic=self.folder/('diagnostic_'+time.strftime('%Y%m%d_%H%M%S')+'.txt')
   self.diagnostic.write_text('',encoding='utf-8')
  except OSError:
   messagebox.showerror('Dossier inaccessible','Choisissez un fichier dans un dossier où vous pouvez enregistrer les résultats.');return
  self.start_button.configure(state='disabled');self.stop_button.configure(state='normal');self.open_button.configure(state='disabled')
  for w in self.inputs:w.configure(state='disabled')
  self.started_at=time.monotonic();self.last_event_at=self.started_at;self.activity.set('Démarrage du moteur…');self.log_button.configure(state='normal')
  self.stage.set('1  Préparation');self.status.set('Nous préparons votre espace de travail…');self.bar.configure(mode='indeterminate');self.bar.start(15)
  try:
   self.proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONUNBUFFERED':'1','PYTHONIOENCODING':'utf-8'},start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  except Exception as e:
   self.record(str(e));self.finish('Impossible de démarrer. Le détail est enregistré dans le fichier de diagnostic.');return
  proc=self.proc
  def read():
   with proc.stdout:
    for line in proc.stdout:self.events.put(('line',line.rstrip()))
   self.events.put(('exit',proc.wait()))
  threading.Thread(target=read,daemon=True).start()
 def poll(self):
  for _ in range(150):
   try:kind,data=self.events.get_nowait()
   except queue.Empty:break
   if kind=='line':self.last_event_at=time.monotonic()
   if kind=='exit':
    result=self.workflow_result if data==0 and not self.stopped else None
    self.finish('Arrêté — relance possible, fichiers terminés conservés.' if self.stopped else ('Vos fichiers sont prêts. Vérifiez le rapport avant l’import.' if data==0 else self.failure_detail or 'La préparation n’a pas pu aboutir. Un diagnostic est disponible dans le dossier des résultats.'))
    if result:
     self.rebuild_preparation=False
     if result['status']=='waiting_images':self.refresh_two_pass(show_status=True)
     else:
      self.stage.set('Préparation · CSV final prêt pour WordPress')
      missing=len(result.get('missing_images',[]))
      self.status.set('CSV final : '+Path(result['final_csv']).name+'. Téléversez les images de '+str(Path(result['images_directory']).name)+'/fichiers_webp dans WordPress, puis importez le CSV. Produits au statut publié.'+(f' Attention : {missing} référence(s) sans image, voir le rapport.' if missing else ''))
    continue
   if data.startswith('ZPSI_PREPARATION '):
    event=json.loads(data[len('ZPSI_PREPARATION '):]);self.record(data)
    self.stage.set(event['stage']);self.status.set(event['message']);self.bar.stop()
    if event.get('total'):
     self.bar.configure(mode='determinate',maximum=event['total'],value=event.get('done') or 0)
    else:
     self.bar.configure(mode='indeterminate');self.bar.start(15)
    self.eta.set('');continue
   if data.startswith('ZPSI_WORKFLOW '):
    self.workflow_result=json.loads(data[len('ZPSI_WORKFLOW '):]);self.record(data);continue
   if data.startswith('ZPSI_LOCAL_IMAGES '):
    event=json.loads(data[len('ZPSI_LOCAL_IMAGES '):]);self.bar.stop();self.bar.configure(mode='determinate',maximum=max(1,event['total']),value=event['done'])
    self.stage.set('Préparation · Étape 2 sur 2');self.status.set(f"Photos préparées : {event['done']}/{event['total']}");self.eta.set('');continue
   if data.startswith('ZPSI_PROGRESS '):
    self.stage.set('2  Préparation des images')
    event=json.loads(data[len('ZPSI_PROGRESS '):]);self.bar.stop();self.bar.configure(mode='determinate',maximum=max(1,event['total']),value=event['done'])
    self.status.set(f"Images : {event['done']}/{event['total']} traitées — {event['downloaded']} téléchargées, {event['existing']} déjà présentes, {event['failed']} en erreur")
    seconds=event['eta'];self.eta.set('Temps estimé pour les images : '+('calcul en cours…' if seconds is None else f'environ {int(seconds)//60} min {int(seconds)%60:02d} s'))
   else:
    self.record(data)
    if data.startswith('ERREUR préparation :'):self.failure_detail=data
    if data.startswith(('Dossiers lus','Recherche élargie','Descriptions :')):
     description=data.startswith('Descriptions :')
     self.stage.set('3  Descriptions' if description else '2  Recherche des images')
     self.status.set('Nous recherchons les descriptions de vos produits…' if description else 'Nous recherchons les photos correspondant à votre facture…');self.bar.stop();self.bar.configure(mode='indeterminate');self.bar.start(15);self.eta.set('Cela peut prendre quelques instants.')
  if self.proc and hasattr(self,'started_at'):
   elapsed=int(time.monotonic()-self.started_at);silent=int(time.monotonic()-self.last_event_at)
   self.activity.set(f'Temps écoulé : {elapsed//60} min {elapsed%60:02d} s' + (f' · Aucune nouvelle information depuis {silent} s ; l’opération peut encore être en cours.' if silent>=15 else ''))
  self.poll_timer=self.after(150,self.poll)
 def open_diagnostic(self):
  if self.diagnostic:self.open_path(self.diagnostic)
 def record(self,text):
  if self.diagnostic:
   try:
    with self.diagnostic.open('a',encoding='utf-8') as f:f.write(text+'\n')
   except OSError:pass
 def finish(self,message):
  self.proc=None;self.bar.stop();self.status.set(message);self.eta.set('')
  if hasattr(self,'started_at'):
   elapsed=int(time.monotonic()-self.started_at);self.activity.set(f'Durée : {elapsed//60} min {elapsed%60:02d} s')
  self.stage.set('Préparation arrêtée' if self.stopped else 'Fin de la préparation')
  self.start_button.configure(state='normal');self.stop_button.configure(state='disabled');self.open_button.configure(state='normal')
  for w in self.inputs:w.configure(state='normal')
  self.select.configure(state='readonly');self.brand_changed(show_status=False)
 def stop(self):
  if self.proc and self.proc.poll() is None:
   self.stopped=True;self.status.set('Arrêt en cours…');self.stop_button.configure(state='disabled')
   if os.name=='nt':subprocess.Popen(['taskkill','/PID',str(self.proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   else:
    try:os.killpg(self.proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
 def open_folder(self):
  if not self.folder:return
  self.open_path(self.folder)
 def open_path(self,path):
  if sys.platform=='win32':os.startfile(path)
  else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)])
 def destroy(self):
  timer=getattr(self,'poll_timer',None)
  if timer:
   self.after_cancel(timer);self.poll_timer=None
  super().destroy()
 def close(self):
  dialog=getattr(self,'shop_dialog',None)
  if dialog is not None and dialog.winfo_exists() and dialog.busy:
   dialog.lift();dialog.status.set('Attendez le résultat de l’opération avant de fermer l’application.');return
  if self.proc and self.proc.poll() is None:
   if not messagebox.askyesno('Arrêter','Arrêter le traitement et fermer ? Les fichiers terminés seront conservés.'):return
   self.stop()
  self.destroy()

if __name__=='__main__':Client().mainloop()
