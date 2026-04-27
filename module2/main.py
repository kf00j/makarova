# ДЕМО-ВЕРСИЯ: работает: "режим по времени", "таблицы", Label светофора, базовое построение маршрута машин - правила ПДД работают (светофоры)
# Нажми "Построить маршрут", затем кликни на машину на карте — она выделится оранжевой рамкой.
# Кликай по клеткам дороги в нужном порядке — так задаётся путь движения; для другой машины просто кликни на неё.
# Нажми "Сохранить маршрут", затем "Старт/Стоп цикла" — машины поедут по заданным маршрутам.
import sys, json, os, sqlite3
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize, QTimer

M        = r"module1\media"
MAP_FILE = r"map.json"
DB_FILE  = r"traffic.db"
LOGO     = f"{M}\\TLgreen.png"
IMG1,IMG2,IMG3,IMG4,IMG5 = f"{M}\\Cbottom.png",f"{M}\\Pedestrain.png",f"{M}\\Block.png",f"{M}\\Zhorizontal.png",f"{M}\\TLyellow.png"
RD1,RD2  = f"{M}\\Rvertical.png",f"{M}\\Rcrossroads.png"
PLACE_IMGS = [IMG1,IMG2,IMG3,IMG4,IMG5]
FREE     = {IMG2,IMG3}
ROT      = {IMG1,IMG2,IMG4,IMG5}
CYCLES   = {IMG1:[IMG1,f"{M}\\BCvertical.png",f"{M}\\GCicon.ico"],
            IMG3:[IMG3,f"{M}\\Stop.png",f"{M}\\Start.png"],
            IMG5:[IMG5,f"{M}\\TLred.png",f"{M}\\TLgreen.png"]}
TL_CYCLE = [f"{M}\\TLred.png",f"{M}\\TLyellow.png",f"{M}\\TLgreen.png"]
TL_STOP  = {f"{M}\\TLred.png",f"{M}\\TLyellow.png"}
DIR_ROT  = {(1,0):0,(0,1):90,(-1,0):180,(0,-1):270}
CELL,COLS,ROWS = 36,21,21
AUTO_MODES  = {"Старт/Стоп цикла","Режим по времени","Режим по транспорту","Тест шаблон","Тест рандом"}
TL_MODE_MAP = {"Диагностика":"Сброс","Восстановление":"Восстановление",
               "Режим по времени":"По времени","Режим по транспорту":"По транспорту",
               "Тест шаблон":"Тест шаблон","Тест рандом":"Тест рандом"}
ROUTES: dict = {}

def init_db():
    con=sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS Traffic_light (Id_light,Car_count_full_run,Car_average_in_minute,Count_color_switches)")
    con.execute("CREATE TABLE IF NOT EXISTS Cars_stats (Car_id,Car_spawn_ticks,Car_exit_ticks)")
    con.commit(); con.close()

def get_px(path,rot=0):
    p=QPixmap(path); return p.transformed(QTransform().rotate(rot)) if rot and not p.isNull() else p

def new_obj(path): return {"path":path,"base":path,"rot":0,"speed":0}

def parse_dict(d): return {tuple(map(int,k.split(","))):v for k,v in d.items()}


class Grid(QWidget):
    def __init__(self,side):
        super().__init__()
        self.setFixedSize(COLS*CELL,ROWS*CELL); self.setMouseTracking(True)
        self.side=side; self.roads,self.objs,self.cars={},{},{}
        self.mode=self.sel=None; self._rcar=None; self._rpts=[]
        self._anim={}; self._anim_timer=QTimer(interval=400,timeout=self._tick)
        self._tip=QLabel(self); self._tip.setStyleSheet("background:#555;color:#fff;padding:2px 4px;border-radius:3px;"); self._tip.hide()

    def mouseMoveEvent(self,e):
        x,y=int(e.position().x()//CELL),int(e.position().y()//CELL)
        if 0<=x<COLS and 0<=y<ROWS: self._tip.setText(f"x:{x} y:{y}"); self._tip.adjustSize(); self._tip.move(int(e.position().x())+10,int(e.position().y())+14); self._tip.show()
        else: self._tip.hide()

    def leaveEvent(self,_): self._tip.hide()

    def paintEvent(self,_):
        p=QPainter(self); p.fillRect(self.rect(),QColor(235,235,235))
        for layer in (self.roads,self.objs,self.cars):
            for (x,y),o in layer.items():
                img=get_px(o["path"],o["rot"])
                if not img.isNull(): p.drawPixmap(x*CELL,y*CELL,CELL,CELL,img)
        if self._rcar:
            p.setPen(QPen(QColor(255,140,0,180),2))
            for x,y in self._rpts: p.drawRect(x*CELL+1,y*CELL+1,CELL-2,CELL-2)
        p.setPen(QPen(QColor(0,0,0,50)))
        for i in range(COLS+1): p.drawLine(i*CELL,0,i*CELL,ROWS*CELL)
        for i in range(ROWS+1): p.drawLine(0,i*CELL,COLS*CELL,i*CELL)

    def mousePressEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton: return
        x,y=int(e.position().x()//CELL),int(e.position().y()//CELL)
        if not(0<=x<COLS and 0<=y<ROWS): return
        c=(x,y)
        if self.mode=='route':
            if c in self.cars: self._commit(); self._rcar=c; self._rpts=[c]
            elif self._rcar and c in self.roads and c not in self._rpts: self._rpts.append(c)
            self.update(); return
        if self.mode=='place' and self.sel:
            if c in self.roads or self.sel in FREE:
                (self.cars if self.sel==IMG1 else self.objs)[c]=new_obj(self.sel)
        else:
            o=self.objs.get(c) or self.cars.get(c)
            if o: self.side.show_props(c,o,self)
        self.update()

    def _commit(self):
        if self._rcar and len(self._rpts)>1: ROUTES[self._rcar]=list(self._rpts)

    def save_route(self): self._commit(); self._rcar=None; self._rpts=[]; self.update()
    def cancel_route(self): self._commit(); self._rcar=None; self._rpts=[]; self.update()

    def start_cycle(self):
        self._anim={k:{"pos":list(k),"step":1} for k,r in ROUTES.items() if k in self.cars and len(r)>1}
        if self._anim: self._anim_timer.start()

    def stop_cycle(self):
        self._anim_timer.stop()
        for k,st in self._anim.items():
            cur=tuple(st["pos"])
            if cur!=k and cur in self.cars: self.cars[k]=self.cars.pop(cur); self.cars[k]["rot"]=0
        self._anim={}; self.update()

    def _tick(self):
        pos={tuple(st["pos"]) for st in self._anim.values()}; done=True
        for k,st in self._anim.items():
            rt=ROUTES[k]
            if st["step"]>=len(rt): continue
            done=False; cur=tuple(st["pos"]); nxt=rt[st["step"]]
            if (any(self.objs.get((nxt[0]+dx,nxt[1]+dy),{}).get("path") in TL_STOP for dx,dy in((0,0),(1,0),(-1,0),(0,1),(0,-1)))
                or self.objs.get(nxt,{}).get("base")==IMG2
                or (nxt in pos and nxt!=cur)): continue
            car=self.cars.pop(cur,None)
            if car: car["rot"]=DIR_ROT.get((nxt[0]-cur[0],nxt[1]-cur[1]),car["rot"]); self.cars[nxt]=car; pos.discard(cur); pos.add(nxt)
            st["pos"]=list(nxt); st["step"]+=1
        if done: self._anim_timer.stop()
        self.update()

    def load(self,path):
        try:
            with open(path,encoding="utf-8") as f: data=json.load(f)
            self.roads=parse_dict(data.get("roads",{})); self.objs=parse_dict(data.get("objs",{}))
            self.cars={k:v for k,v in self.objs.items() if v["base"]==IMG1}
            self.objs={k:v for k,v in self.objs.items() if v["base"]!=IMG1}
            self.update()
        except Exception: pass


class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120); self.grid=None; self.ibtns=[]
        vb=QVBoxLayout(self); vb.setContentsMargins(6,6,6,6); vb.setSpacing(4)
        self.sp=self._sec(PLACE_IMGS); self.props=QWidget(); self.pvb=QVBoxLayout(self.props)
        self.pvb.setContentsMargins(0,0,0,0); self.pvb.setSpacing(4)
        for w in (self.sp,self.props): w.hide(); vb.addWidget(w)
        vb.addStretch()
        self.tl_lbl=QLabel("Режим светофоров:\nСтандартный"); self.mode_lbl=QLabel("Текущий режим:\nСтандартный")
        for l in (self.tl_lbl,self.mode_lbl): l.setWordWrap(True); l.setStyleSheet("font-size:10px;color:#444;"); vb.addWidget(l)

    def set_mode(self,name):
        self.tl_lbl.setText(f"Режим светофоров:\n{TL_MODE_MAP.get(name,'Стандартный')}")
        self.mode_lbl.setText(f"Текущий режим:\n{'Автоматический' if name in AUTO_MODES else 'Стандартный'}")

    def _sec(self,paths):
        w=QWidget(); vb=QVBoxLayout(w); vb.setContentsMargins(0,0,0,0)
        for p in paths:
            b=QPushButton(); b.setFixedSize(100,100); b.setCheckable(True); b.setProperty("path",p)
            ic=get_px(p)
            if not ic.isNull(): b.setIcon(QIcon(ic)); b.setIconSize(QSize(88,88))
            else: b.setText(os.path.basename(p)[:8])
            b.clicked.connect(self._pick); vb.addWidget(b); self.ibtns.append(b)
        return w

    def _pick(self):
        s=self.sender()
        for b in self.ibtns:
            if b is not s: b.setChecked(False)
        if self.grid: self.grid.sel=s.property("path") if s.isChecked() else None

    def switch(self,place=False,route=False):
        for b in self.ibtns: b.setChecked(False)
        if self.grid:
            self.grid.sel=None; self.grid.mode='place' if place else('route' if route else None)
            if not route: self.grid.cancel_route()
        self.props.hide(); self.sp.setVisible(place)

    def show_props(self,cell,o,grid):
        while self.pvb.count():
            w=self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
        self.props.show(); base=o["base"]
        self.pvb.addWidget(QLabel(f"<b>{os.path.basename(base)}</b>"))
        if base in ROT:
            b=QPushButton("Повернуть"); b.clicked.connect(lambda:(o.update(rot=(o["rot"]+90)%360),grid.update())); self.pvb.addWidget(b)
        if base in CYCLES:
            b=QPushButton("Изменить тип"); cy=CYCLES[base]
            def color(_,obj=o,c=cy): i=c.index(obj["path"]) if obj["path"] in c else 0; obj["path"]=c[(i+1)%len(c)]; grid.update()
            b.clicked.connect(color); self.pvb.addWidget(b)
        if base==IMG2:
            lbl=QLabel(f"Скорость: {o.get('speed',0)} сек"); self.pvb.addWidget(lbl)
            for txt,d in(("+1",1),("-1",-1)):
                b=QPushButton(txt)
                def spd(_,obj=o,dv=d,l=lbl): obj["speed"]=obj.get("speed",0)+dv; l.setText(f"Скорость: {obj['speed']} сек")
                b.clicked.connect(spd); self.pvb.addWidget(b)
        b=QPushButton("Удалить"); b.setStyleSheet("color:red;")
        def dele(_,c=cell,g=grid): g.objs.pop(c,None); g.cars.pop(c,None); g.update(); self.props.hide()
        b.clicked.connect(dele); self.pvb.addWidget(b)


def show_tables():
    dlg=QDialog(); dlg.setWindowTitle("Таблицы"); vb=QVBoxLayout(dlg)
    con=sqlite3.connect(DB_FILE)
    for name,cols in [("Traffic_light",["Id_light","Car_count_full_run","Car_average_in_minute","Count_color_switches"]),
                      ("Cars_stats",["Car_id","Car_spawn_ticks","Car_exit_ticks"])]:
        vb.addWidget(QLabel(f"<b>{name}</b>"))
        rows=con.execute(f"SELECT * FROM {name}").fetchall()
        t=QTableWidget(len(rows),len(cols)); t.setHorizontalHeaderLabels(cols)
        for r,row in enumerate(rows):
            for c,val in enumerate(row): t.setItem(r,c,QTableWidgetItem(str(val)))
        t.setFixedHeight(120); vb.addWidget(t)
    con.close(); dlg.exec()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp=QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))
        self.side=Side(); self.grid=Grid(self.side); self.side.grid=self.grid
        self._tl_idx=0; self._tl_timer=QTimer(interval=5000,timeout=self._tl_tick)

        c=QWidget(); self.setCentralWidget(c)
        root=QVBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        body.addWidget(self.side); body.addWidget(self.grid); root.addLayout(body)

        bar1=QHBoxLayout(); bar1.setContentsMargins(6,6,6,2); bar1.setSpacing(6)
        self.bp=QPushButton("Добавить объекты"); self.bp.setCheckable(True)
        self.brt=QPushButton("Построить маршрут"); self.brt.setCheckable(True)
        self.brs=QPushButton("Сохранить маршрут")
        self.bp.toggled.connect(lambda v:(self.brt.setChecked(False),self.side.switch(place=v),self.side.set_mode("" if v else "")))
        self.brt.toggled.connect(lambda v:(self.bp.setChecked(False),self.side.switch(route=v)))
        self.brs.clicked.connect(self.grid.save_route)
        for b in(self.bp,self.brt,self.brs):
            b.setFixedHeight(32); b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed); bar1.addWidget(b)
        root.addLayout(bar1)

        bar2=QHBoxLayout(); bar2.setContentsMargins(6,2,6,6); bar2.setSpacing(6)
        for name,chk,slot in[
            ("Диагностика",False,lambda:self.side.set_mode("Диагностика")),
            ("Восстановление",False,lambda:self.side.set_mode("Восстановление")),
            ("Старт/Стоп цикла",True,self._toggle_cycle),
            ("Режим по времени",True,self._toggle_time),
            ("Режим по транспорту",False,lambda:self.side.set_mode("Режим по транспорту")),
            ("Тест шаблон",False,lambda:self.side.set_mode("Тест шаблон")),
            ("Тест рандом",False,lambda:self.side.set_mode("Тест рандом")),
            ("Таблицы",False,lambda:(self.side.set_mode("Таблицы"),show_tables())),
        ]:
            b=QPushButton(name); b.setFixedHeight(32); b.setCheckable(chk)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot); bar2.addWidget(b)
            if name=="Старт/Стоп цикла": self._btn_cycle=b
            if name=="Режим по времени": self._btn_time=b
        root.addLayout(bar2); self.adjustSize(); self.grid.load(MAP_FILE)

    def _toggle_cycle(self):
        if self._btn_cycle.isChecked(): self.grid.start_cycle(); self.side.set_mode("Старт/Стоп цикла")
        else: self.grid.stop_cycle(); self.side.set_mode("")

    def _toggle_time(self):
        if self._btn_time.isChecked(): self._tl_idx=0; self._tl_tick(); self._tl_timer.start(); self.side.set_mode("Режим по времени")
        else:
            self._tl_timer.stop()
            for o in self.grid.objs.values():
                if o["base"]==IMG5: o["path"]=IMG5
            self.grid.update(); self.side.set_mode("")

    def _tl_tick(self):
        state=TL_CYCLE[self._tl_idx%3]
        for o in self.grid.objs.values():
            if o["base"]==IMG5: o["path"]=state
        self._tl_idx+=1; self.grid.update()

if __name__=="__main__":
    init_db(); app=QApplication(sys.argv); App().show(); sys.exit(app.exec())
