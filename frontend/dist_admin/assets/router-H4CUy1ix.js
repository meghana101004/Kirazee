import{r as u,R as V}from"./antd-D0Wykf3W.js";/**
 * @remix-run/router v1.23.0
 *
 * Copyright (c) Remix Software Inc.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE.md file in the root directory of this source tree.
 *
 * @license MIT
 */function P(){return P=Object.assign?Object.assign.bind():function(t){for(var e=1;e<arguments.length;e++){var r=arguments[e];for(var n in r)Object.prototype.hasOwnProperty.call(r,n)&&(t[n]=r[n])}return t},P.apply(this,arguments)}var m;(function(t){t.Pop="POP",t.Push="PUSH",t.Replace="REPLACE"})(m||(m={}));const O="popstate";function N(t){t===void 0&&(t={});function e(n,a){let{pathname:h,search:i,hash:s}=n.location;return E("",{pathname:h,search:i,hash:s},a.state&&a.state.usr||null,a.state&&a.state.key||"default")}function r(n,a){return typeof a=="string"?a:B(a)}return H(e,r,null,t)}function A(t,e){if(t===!1||t===null||typeof t>"u")throw new Error(e)}function W(){return Math.random().toString(36).substr(2,8)}function L(t,e){return{usr:t.state,key:t.key,idx:e}}function E(t,e,r,n){return r===void 0&&(r=null),P({pathname:typeof t=="string"?t:t.pathname,search:"",hash:""},typeof e=="string"?M(e):e,{state:r,key:e&&e.key||n||W()})}function B(t){let{pathname:e="/",search:r="",hash:n=""}=t;return r&&r!=="?"&&(e+=r.charAt(0)==="?"?r:"?"+r),n&&n!=="#"&&(e+=n.charAt(0)==="#"?n:"#"+n),e}function M(t){let e={};if(t){let r=t.indexOf("#");r>=0&&(e.hash=t.substr(r),t=t.substr(0,r));let n=t.indexOf("?");n>=0&&(e.search=t.substr(n),t=t.substr(0,n)),t&&(e.pathname=t)}return e}function H(t,e,r,n){n===void 0&&(n={});let{window:a=document.defaultView,v5Compat:h=!1}=n,i=a.history,s=m.Pop,l=null,c=p();c==null&&(c=0,i.replaceState(P({},i.state,{idx:c}),""));function p(){return(i.state||{idx:null}).idx}function g(){s=m.Pop;let o=p(),f=o==null?null:o-c;c=o,l&&l({action:s,location:d.location,delta:f})}function y(o,f){s=m.Push;let v=E(d.location,o,f);c=p()+1;let R=L(v,c),S=d.createHref(v);try{i.pushState(R,"",S)}catch(b){if(b instanceof DOMException&&b.name==="DataCloneError")throw b;a.location.assign(S)}h&&l&&l({action:s,location:d.location,delta:1})}function x(o,f){s=m.Replace;let v=E(d.location,o,f);c=p();let R=L(v,c),S=d.createHref(v);i.replaceState(R,"",S),h&&l&&l({action:s,location:d.location,delta:0})}function w(o){let f=a.location.origin!=="null"?a.location.origin:a.location.href,v=typeof o=="string"?o:B(o);return v=v.replace(/ $/,"%20"),A(f,"No window.location.(origin|href) available to create URL for href: "+v),new URL(v,f)}let d={get action(){return s},get location(){return t(a,i)},listen(o){if(l)throw new Error("A history only accepts one active listener");return a.addEventListener(O,g),l=o,()=>{a.removeEventListener(O,g),l=null}},createHref(o){return e(a,o)},createURL:w,encodeLocation(o){let f=w(o);return{pathname:f.pathname,search:f.search,hash:f.hash}},push:y,replace:x,go(o){return i.go(o)}};return d}var T;(function(t){t.data="data",t.deferred="deferred",t.redirect="redirect",t.error="error"})(T||(T={}));function $(t,e){if(e==="/")return t;if(!t.toLowerCase().startsWith(e.toLowerCase()))return null;let r=e.endsWith("/")?e.length-1:e.length,n=t.charAt(r);return n&&n!=="/"?null:t.slice(r)||"/"}const j=["post","put","patch","delete"];new Set(j);const q=["get",...j];new Set(q);/**
 * React Router v6.30.1
 *
 * Copyright (c) Remix Software Inc.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE.md file in the root directory of this source tree.
 *
 * @license MIT
 */function C(){return C=Object.assign?Object.assign.bind():function(t){for(var e=1;e<arguments.length;e++){var r=arguments[e];for(var n in r)Object.prototype.hasOwnProperty.call(r,n)&&(t[n]=r[n])}return t},C.apply(this,arguments)}const K=u.createContext(null),F=u.createContext(null);function z(){return u.useContext(F)!=null}function G(t,e){t?.v7_startTransition,t?.v7_relativeSplatPath}function J(t){let{basename:e="/",children:r=null,location:n,navigationType:a=m.Pop,navigator:h,static:i=!1,future:s}=t;z()&&A(!1);let l=e.replace(/^\/*/,"/"),c=u.useMemo(()=>({basename:l,navigator:h,static:i,future:C({v7_relativeSplatPath:!1},s)}),[l,s,h,i]);typeof n=="string"&&(n=M(n));let{pathname:p="/",search:g="",hash:y="",state:x=null,key:w="default"}=n,d=u.useMemo(()=>{let o=$(p,l);return o==null?null:{location:{pathname:o,search:g,hash:y,state:x,key:w},navigationType:a}},[l,p,g,y,x,w,a]);return d==null?null:u.createElement(K.Provider,{value:c},u.createElement(F.Provider,{children:r,value:d}))}new Promise(()=>{});/**
 * React Router DOM v6.30.1
 *
 * Copyright (c) Remix Software Inc.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE.md file in the root directory of this source tree.
 *
 * @license MIT
 */const Q="6";try{window.__reactRouterVersion=Q}catch{}const X="startTransition",U=V[X];function Z(t){let{basename:e,children:r,future:n,window:a}=t,h=u.useRef();h.current==null&&(h.current=N({window:a,v5Compat:!0}));let i=h.current,[s,l]=u.useState({action:i.action,location:i.location}),{v7_startTransition:c}=n||{},p=u.useCallback(g=>{c&&U?U(()=>l(g)):l(g)},[l,c]);return u.useLayoutEffect(()=>i.listen(p),[i,p]),u.useEffect(()=>G(n),[n]),u.createElement(J,{basename:e,children:r,location:s.location,navigationType:s.action,navigator:i,future:n})}var I;(function(t){t.UseScrollRestoration="useScrollRestoration",t.UseSubmit="useSubmit",t.UseSubmitFetcher="useSubmitFetcher",t.UseFetcher="useFetcher",t.useViewTransitionState="useViewTransitionState"})(I||(I={}));var _;(function(t){t.UseFetcher="useFetcher",t.UseFetchers="useFetchers",t.UseScrollRestoration="useScrollRestoration"})(_||(_={}));export{Z as B};
//# sourceMappingURL=router-H4CUy1ix.js.map
