const V={}, LS={}, PR={}, IO={mx:0,my:0,md:false,keys:{},t:0,gfx:0};
function L(nm){return LS[nm]||(LS[nm]=[]);}
function n(x){if(typeof x==='number')return isNaN(x)?0:x;if(typeof x==='boolean')return x?1:0;const v=Number(x);return isNaN(v)||(typeof x==='string'&&x.trim()==='')?0:v;}
function s(x){return typeof x==='string'?x:String(x);}
function b(x){if(typeof x==='boolean')return x;if(typeof x==='string')return !(x===''||x==='0'||x.toLowerCase()==='false');return !!x;}
function ws(x){return typeof x==='string'&&x.trim()==='';}
function cmp(a,b_){let n1=Number(a),n2=Number(b_);if(n1===0&&ws(a))n1=NaN;if(n2===0&&ws(b_))n2=NaN;if(isNaN(n1)||isNaN(n2)){const s1=String(a).toLowerCase(),s2=String(b_).toLowerCase();return s1<s2?-1:s1>s2?1:0;}return n1-n2;}
function mod(a,b_){let r=a%b_;if(r/b_<0)r+=b_;return r;}
function isint(x){return typeof x==='number'?Number.isInteger(x):!String(x).includes('.');}
function rnd(a,b_){let lo=n(a),hi=n(b_);if(lo>hi)[lo,hi]=[hi,lo];if(isint(a)&&isint(b_))return lo+Math.floor(Math.random()*(hi-lo+1));return Math.random()*(hi-lo)+lo;}
function mop(op,x){const r=Math.PI/180;switch(op){case'sqrt':return Math.sqrt(x);case'abs':return Math.abs(x);case'floor':return Math.floor(x);case'ceiling':return Math.ceil(x);
case'sin':return parseFloat(Math.sin(x*r).toFixed(10));case'cos':return parseFloat(Math.cos(x*r).toFixed(10));case'atan':return Math.atan(x)/r;}throw op;}
function idx(l,i){i=Math.floor(n(i));return (i<1||i>l.length)?-1:i-1;}
function li(nm,i){const l=L(nm);const k=idx(l,i);return k<0?'':l[k];}
function lset(nm,i,v){const l=L(nm);const k=idx(l,i);if(k>=0)l[k]=v;}
function ldel(nm,i){const l=L(nm);const k=idx(l,i);if(k>=0)l.splice(k,1);}
function lins(nm,i,v){const l=L(nm);i=Math.floor(n(i));if(i>=1&&i<=l.length+1)l.splice(i-1,0,v);}
function lidx(nm,v){const l=L(nm);for(let i=0;i<l.length;i++)if(cmp(l[i],v)===0)return i+1;return 0;}
