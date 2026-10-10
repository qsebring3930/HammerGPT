"""Read-only diagnostics for failed continuous frontage construction."""
import json,sys
from pathlib import Path
import free_mid_layout as m

def trace(frame,event,arg):
 if event=='exception' and frame.f_code.co_name=='generate':
  x=frame.f_locals
  if 'straight' in x:
   print(json.dumps({'edges':[{'length':q.length,'coordinates':list(q.coords)} for q in x['straight']], 'core':list(x['g'].exterior.coords),'route':x['route']}))
 return trace

if __name__=='__main__':
 folder=Path(sys.argv[1]);base=json.loads((folder/'composition.json').read_text());spec=json.loads((folder/'resolved-specification.json').read_text())
 sys.settrace(trace)
 try:m.generate(base,spec,int(sys.argv[2]))
 except ValueError as e:print(str(e))
 finally:sys.settrace(None)
