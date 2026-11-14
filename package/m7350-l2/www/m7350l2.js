/* Appended to settings.min.js by tools/build-www.py. */
!function(a){"use strict";
var timer,visit=0,visible=false,pending=false,loaded=false,editing="",busy=false,creating=false,syncing=false,
 switchTarget="",switchDeadline=0,statusGeneration=0,modeReady=false,lastModeError="",
 names={factory:"OEM",vpn:"VPN",home:"VPN",provider:"VPN",dirty:"Mixed (cleanup needed)"},
 keys=["server","dns","user","auth","mtu","vni","port"];
function el(id){return a("#"+id)}
function value(id){return el(id).val()}
function choose(id, selected){
 var field=el(id), index=field.find("option").filter(function(){return this.value===selected}).index();
 if(index<0)return;
 syncing=true;field.dropdown("select",index);syncing=false;
}
function setToggle(id,checked){el(id).switchButton("changeState",checked,true,true)}
function labelFor(slot){return slot}
var proposalTypes=["ike","esp"];
var networks=["lte","l3","l2"];
function wifiFields(network,checked){el("m7wifi-"+network+"-row").toggleClass("hide",!checked)}
function token(){try{if(window.AuthModel&&AuthModel.getToken){var t=AuthModel.getToken();if(t)return t}}catch(e){}
 var m=document.cookie.match(/(?:^|;\s*)tpweb_token=([^;]*)/);return m?decodeURIComponent(m[1]):""}
function call(data,done){var requestVisit=visit;data.token=token();
 a.ajax({url:"cgi-bin/m7350l2",type:"POST",data:data,dataType:"json",cache:false,timeout:5000,
  success:function(r){if(requestVisit!==visit)return;if(r&&r.result===-3&&!switchTarget){window.location.href="login.html";return}done(r||{result:-1,error:"empty response"})},
  error:function(){if(requestVisit===visit)done({result:-1,error:"request failed",transport:true})}})}
function text(id,v){el(id).text(v==null||v===""?"-":v)}
function rememberSwitch(deadline){
 try{
  if(deadline)window.sessionStorage.setItem("m7350-mode-switch",String(deadline));
  else window.sessionStorage.removeItem("m7350-mode-switch");
 }catch(error){}
}
function showFailure(){
 el("m7l2FailureDetails").addClass("hide");
 text("m7l2FailureReason","Loading…");
 call({action:"last_failure",summary:"1"},function(r){
  if(r.result!==0){text("m7l2FailureReason",r.error||"Could not load the last failure.");return}
  var matches=!lastModeError||r.reason&&lastModeError.indexOf(r.reason)===0;
  text("m7l2FailureReason",(matches?r.reason:lastModeError)||"No failure recorded since startup.");
  if(!matches)r.time="";
  el("m7l2FailureTime").toggleClass("hide",!r.time).attr("datetime",r.time||null)
   .text(r.time?r.time.replace("T"," ").replace(/Z$/," UTC"):"");
  el("m7l2FailureDetails").toggleClass("hide",!r.reason&&!lastModeError);
 });
}
function show(r){if(!visible)return;
 if(r.result!==0){
  clearTimeout(timer);
  if(switchTarget){
   if(r.result===-3)reconnect();else retrySwitch();
   return
  }
  timer=setTimeout(refresh,2000);return
 }
 if(switchTarget&&r.switching&&Date.now()>=switchDeadline){
  finishReconnect("The switch is still running. Reload this page to check the mode.");
  return
 }
 text("m7l2Active",r.active==="factory"?"VPN Off":names[r.active]||r.active);
 el("m7l2ActiveRow").toggleClass("hide",r.active===r.desired);
 text("m7l2Running",labelFor(r.active_profile));
 el("m7l2TunnelRow").toggleClass("hide",["vpn","home","provider"].indexOf(r.active)<0);
 text("m7l2Tunnels","L2TP "+r.tunnel1+", VXLAN "+r.l2_tunnel);
 el("m7l2Busy").toggleClass("hide",!r.switching&&!switchTarget);
 if(switchTarget&&!r.switching&&!pending){
  switchTarget="";
  rememberSwitch(0);
  el("m7l2Busy").addClass("hide");
 }
 if(!r.switching&&!pending&&(r.last_error||"")!==lastModeError){
  lastModeError=r.last_error||"";
  var failure=el("m7l2Failure");
  if(failure.prop("open"))showFailure();
  else if(lastModeError)failure.prop("open",true);
 }
 if(el("m7l2Mode").length){
  var locked=r.switching||pending||!!switchTarget;
  var desiredMode=r.desired==="factory"?"factory":"vpn";
  if(!locked&&!el("m7l2Mode").data("touched")&&value("m7l2Mode")!==desiredMode)
   choose("m7l2Mode",desiredMode);
  modeReady=!locked;
  el("m7l2Mode").dropdown(locked?"disable":"enable");
  el("m7l2Apply").prop("disabled",locked);
 }
 var h=r.home||{};
 if(!loaded){
  el("m7l2HomeSsid").val(h.ssid);el("m7l2HomeL3").val(h.ssid_l3);
  el("m7l2HomeLte").val(h.ssid_lte);
  networks.forEach(function(n){
   var checked=!!h["wifi_"+n+"_custom"];
   setToggle("m7wifi-"+n+"-custom",checked);wifiFields(n,checked);
   el("m7wifi-"+n+"-key").attr("placeholder",checked?"Leave empty to keep":"");
  });
  loaded=true;
 }
 el("m7l2HomeWifiState").text(h.wifi_set?"(set; leave empty to keep)":"(uses OEM Wi-Fi password)");
 clearTimeout(timer);timer=setTimeout(refresh,r.switching?2000:10000)}
function refresh(){
 var generation=++statusGeneration;
 call({action:"status"},function(r){if(generation===statusGeneration)show(r)})
}
function reconnect(){
 var requestVisit=visit;
 a.ajax({url:"cgi-bin/m7350l2?switch-state",dataType:"json",timeout:5000})
  .done(function(r){
   if(requestVisit!==visit)return;
   if(!r||r.switching||["OEM","VPN","Unavailable"].indexOf(r.mode)<0){retrySwitch();return}
   // The public status cannot tell whether the browser session survived.
   call({action:"status"},function(status){
    if(status.result===-3){
     finishReconnect("Your session ended. Sign in to continue.",true);
    }else if(status.result===0){
     show(status);
    }else{
     retrySwitch();
    }
   });
  }).fail(function(){if(requestVisit===visit)retrySwitch()});
}
function retrySwitch(){
 if(Date.now()>=switchDeadline){
  finishReconnect("Could not confirm the running mode. Reload this page to check.");
  return
 }
 timer=setTimeout(refresh,2000);
}
function finishReconnect(message,signIn){
 switchTarget="";
 rememberSwitch(0);
 el("m7l2Busy").addClass("hide");
 el("m7l2TunnelRow").addClass("hide");
 el("m7l2ActiveRow").addClass("hide");
 el("m7l2Mode").closest(".content-group").addClass("hide");
 el("m7l2Apply").addClass("hide");
 text("m7l2SwitchMsg",message);
 el("m7l2SignIn").toggleClass("hide",!signIn);
}
function l2Fields(){el("m7vpn-l2-fields").toggleClass("hide",!el("m7vpn-l2").prop("checked"))}
function proposalFields(type){
 var id="m7vpn-"+type;
 el(id+"-custom").toggleClass("hide",value(id+"-suite")!=="custom");
}
function showProposal(type,proposal){
 var id="m7vpn-"+type, suite=el(id+"-suite");
 var preset=suite.find("option").filter(function(){
  return this.value!=="custom"&&this.value===proposal;
 }).length>0;
 choose(id+"-suite",preset?proposal:"custom");
 el(id).val(preset?"":proposal);
 proposalFields(type);
}
function profile(action,slot){
 if(busy)return;
 if(action==="vpn_create"&&!/^[a-z][a-z0-9-]{0,23}$/.test(slot)){text("m7l2SaveMsg","Enter a profile ID such as office");return;}
 var req={action:action,slot:slot};
 if(action==="vpn_rename"){
  req.new_slot=value("m7l2RenameId");
  if(!/^[a-z][a-z0-9-]{0,23}$/.test(req.new_slot)||req.new_slot===slot){
   text("m7l2SaveMsg","Enter a different profile ID using lowercase letters, digits or hyphens.");return
  }
 }
 if(action==="vpn_save"||action==="vpn_create"){
  keys.forEach(function(k){req[k]=value("m7vpn-"+k)});
  proposalTypes.forEach(function(type){
   var id="m7vpn-"+type, suite=value(id+"-suite");
   req[type]=suite==="custom"?value(id):suite;
  });
  req.l2=el("m7vpn-l2").prop("checked")?"1":"0";
  req.usb_network=value("m7vpn-usb_network");
  if(req.usb_network==="l2"&&req.l2!=="1"){text("m7l2SaveMsg","Enable L2 to use it for USB.");return}
  req.password=value("m7vpn-password");req.psk=value("m7vpn-psk");
 }
 busy=true;
 el("m7l2Slot").dropdown("disable");
 a("#m7l2Save,#m7l2Select,#m7l2Create,#m7l2Cancel,#m7l2Delete,#m7l2Rename,#m7l2RenameApply").prop("disabled",true);
 call(req,function(r){
  busy=false;
  if(!visible)return;
  el("m7l2Slot").dropdown("enable");
  a("#m7l2Save,#m7l2Create,#m7l2Cancel").prop("disabled",false);
  el("m7l2Select").prop("disabled",creating||!editing);
  el("m7l2Save").prop("disabled",!creating&&!editing);
  el("m7l2Delete").prop("disabled",creating);
  el("m7l2Rename").prop("disabled",creating||!editing);
  el("m7l2RenameApply").prop("disabled",false);
  if(r.result!==0){
   if(action==="vpn_get")choose("m7l2Slot",editing);
   text("m7l2SaveMsg",r.error);return;
  }
  creating=false;el("m7l2NewProfile").addClass("hide");
  el("m7l2RenameProfile").addClass("hide");
  editing=r.slot;
  var list=el("m7l2Slot");
  list.dropdown("clear");
  r.profiles.forEach(function(slot){list.dropdown("addItem",labelFor(slot),slot)});
  el("m7l2Delete").toggleClass("hide",!editing).prop("disabled",!editing);
  el("m7l2Rename").toggleClass("hide",!editing).prop("disabled",!editing);
  if(editing)choose("m7l2Slot",editing);
  el("m7l2Select").prop("disabled",!editing);
  el("m7l2Save").prop("disabled",!editing);
  if(action==="vpn_rename"){
   text("m7l2Selected",labelFor(r.selected));
   text("m7l2SaveMsg","Profile renamed");
   return;
  }
  keys.forEach(function(k){if(k==="auth")choose("m7vpn-auth",r[k]);else el("m7vpn-"+k).val(r[k])});
  proposalTypes.forEach(function(type){showProposal(type,r[type])});
  setToggle("m7vpn-l2",r.l2==="1");l2Fields();
  choose("m7vpn-usb_network",r.usb_network);
  el("m7vpn-password").val("").attr("placeholder",r.password_set?"Leave empty to keep":"");
  el("m7vpn-psk").val("").attr("placeholder",r.psk_set?"Leave empty to keep":"");
  text("m7l2Selected",labelFor(r.selected));
  el("m7l2SaveMsg").text((action==="vpn_save"||action==="vpn_create")?"Profile saved":action==="vpn_select"?"VPN profile saved for activation and startup":action==="vpn_delete"?"Profile deleted":!editing?"No profiles. Click Create to add one.":"");
 });
}
function activate(mode){
 if(!modeReady||pending||switchTarget)return;
 clearTimeout(timer);
 statusGeneration++;
 switchTarget=mode;switchDeadline=Date.now()+120000;
 rememberSwitch(switchDeadline);
 pending=true;el("m7l2Apply").prop("disabled",true);
 el("m7l2Mode").dropdown("disable");
 el("m7l2Busy").removeClass("hide");el("m7l2SwitchMsg").empty();
 call({action:"set",mode:mode},function(r){
  pending=false;
  el("m7l2Mode").data("touched",false);
  if(r.result!==0&&!r.transport&&r.result!==-3){
   switchTarget="";
   rememberSwitch(0);
   el("m7l2Busy").addClass("hide");
   el("m7l2Apply").prop("disabled",false);
   el("m7l2Mode").dropdown("enable");
   text("m7l2SwitchMsg",r.error||"Could not apply mode.");
   timer=setTimeout(refresh,10000);
   return
  }
  if(r.result!==0){retrySwitch();return}
  timer=setTimeout(refresh,1500);
 });
}
var vpnPage={onLoad:function(){
 visit++;visible=true;pending=false;loaded=false;busy=false;editing="";creating=false;switchTarget="";
 modeReady=false;lastModeError="";
 // Disable after initialization so the OEM widget removes its initial click handlers.
 el("m7l2Mode").data("touched",false).dropdown({onChanged:function(){
  if(modeReady&&!syncing)el("m7l2Mode").data("touched",true);
 }}).dropdown("disable");
 el("m7vpn-usb_network").dropdown();
 el("m7vpn-auth").dropdown();
 proposalTypes.forEach(function(type){
  el("m7vpn-"+type+"-suite").dropdown({onChanged:function(){proposalFields(type)}});
 });
 el("m7vpn-l2").switchButton({onChanged:l2Fields});
 networks.forEach(function(n){
  el("m7wifi-"+n+"-custom").switchButton({onChanged:function(checked){wifiFields(n,checked)}});
 });
 el("m7l2Apply").on("click",function(){activate(value("m7l2Mode"))});
 el("m7l2Failure").on("toggle",function(){if(this.open)showFailure()});
 el("m7l2Slot").dropdown({onChanged:function(){
  if(!syncing)profile("vpn_get",value("m7l2Slot"));
 }});
 el("m7l2Create").on("click",function(){
  creating=true;el("m7l2Save").prop("disabled",false);el("m7l2NewProfile").removeClass("hide");el("m7l2NewId").val("").focus();
  el("m7l2Select").prop("disabled",true);
  el("m7l2Delete").addClass("hide").prop("disabled",true);
  el("m7l2Rename").addClass("hide").prop("disabled",true);
  el("m7l2RenameProfile").addClass("hide");
  keys.forEach(function(k){
   if(k!=="auth")el("m7vpn-"+k).val("");
  });
  ["password","psk"].forEach(function(k){
   el("m7vpn-"+k).val("").removeAttr("placeholder");
  });
  choose("m7vpn-auth","chap");
  choose("m7vpn-usb_network","lte");
  proposalTypes.forEach(function(type){
   showProposal(type,el("m7vpn-"+type+"-suite").find("option").first().val());
  });
  el("m7vpn-vni").val("7350");el("m7vpn-port").val("4789");
  setToggle("m7vpn-l2",false);l2Fields();
  text("m7l2SaveMsg","Enter the new profile details, then Save.");
 });
 el("m7l2Cancel").on("click",function(){profile("vpn_get",editing)});
 el("m7l2Save").on("click",function(){profile(creating?"vpn_create":"vpn_save",creating?value("m7l2NewId"):editing)});
 el("m7l2Select").on("click",function(){profile("vpn_select",editing)});
 el("m7l2Rename").on("click",function(){
  if(busy||creating||!editing)return;
  var row=el("m7l2RenameProfile");
  row.toggleClass("hide");
  if(!row.hasClass("hide"))el("m7l2RenameId").val(editing).focus();
 });
 el("m7l2RenameApply").on("click",function(){profile("vpn_rename",editing)});
 var deleteDialog=el("m7l2DeleteDialog")[0], deleteSlot="";
 el("m7l2Delete").on("click",function(){
  if(busy||creating||!editing||deleteDialog.open)return;
  deleteSlot=editing;
  deleteDialog.returnValue="";
  text("m7l2DeleteWarning",'Delete "'+deleteSlot+'"? Its saved credentials will be removed.');
  deleteDialog.showModal();
 });
 el("m7l2DeleteDialog").on("close",function(){
  var slot=deleteSlot;
  deleteSlot="";
  if(visible&&!creating&&slot===editing&&this.returnValue==="delete")
   profile("vpn_delete",slot);
 });
 el("m7l2HomeSave").on("click",function(){
  var request={action:"wifi_profile",ssid:value("m7l2HomeSsid"),ssid_l3:value("m7l2HomeL3"),
   ssid_lte:value("m7l2HomeLte")};
  networks.forEach(function(n){
   request["custom_"+n]=el("m7wifi-"+n+"-custom").prop("checked")?"1":"0";
   request["key_"+n]=value("m7wifi-"+n+"-key");
  });
  call(request,function(r){
   text("m7l2HomeSaveMsg",r.result===0?"Saved for next activation":r.error);
   if(r.result===0){
    networks.forEach(function(n){el("m7wifi-"+n+"-key").val("")});
    loaded=false;show(r);
   }
  });
 });
 if(el("m7l2Slot").length)profile("vpn_get","");
 refresh();
},onLeave:function(){
 visit++;visible=false;clearTimeout(timer);
 var dialog=el("m7l2DeleteDialog")[0];
 if(dialog&&dialog.open)dialog.close();
}};
var vpnLogRequest=0;
Settings.m7350VpnLog={
 preselect:function(){
  if(location.hash==="#Advanced/Device/SysLog?type=vpn")el("logTypeSelect").val("7");
 },
 selected:function(){return value("logTypeSelect")==="7"},
 page:function(page,size,levels){
  var section=el("sysLogSection")[0], request=++vpnLogRequest;
  var selected=this.selected();
  el("clearLog").toggle(!selected);
  el("downloadLogLink").toggle(!selected);
  if(!selected)return false;
  page=Math.max(page,1);
  call({action:"vpn_log",level:el("logLevelSelect").dropdown("pos")},function(r){
   if(request!==vpnLogRequest||el("sysLogSection")[0]!==section||!Settings.m7350VpnLog.selected())return;
   var header=el("sysLogHeaderRow"), rows=r.entries||[];
   header.nextAll().remove();
   if(r.result!==0){
    header.after(a("<tr>").append(a("<td>").attr("colspan",5).text(r.error)));
    el("sysLogPagination").pagination("pageCount",0);
    return;
   }
   rows.reverse();
   var start=(page-1)*size, rendered=[];
   rows.slice(start,start+size).forEach(function(row,index){
    var tr=a("<tr>");
    [start+index+1,row.time,"VPN",levels[row.level]].forEach(function(cell){
     tr.append(a("<td>").text(cell));
    });
    tr.append(a("<td>").addClass("m7350-vpn-log-message").text(row.message));
    rendered.push(tr[0]);
   });
   header.after(rendered);
   el("sysLogPagination").pagination("pageCount",rows.length/size);
  });
  return true;
 }
};
Settings.m7350l2=Settings.m7350VpnProfiles=Settings.m7350VpnWifi=vpnPage;
Settings.m7350VpnClients=function(){
 var oem=el("clientListSection");
 var panel=a("<div>").addClass("section-content hide").attr("id","m7350VpnClients").insertAfter(oem);
 var operation=a("<div>").addClass("operation").appendTo(panel);
 var refresh=a("<button>").attr("type","button").addClass("btn btn-info").text("Refresh").appendTo(operation);
 var message=a("<p>").attr("role","status").appendTo(panel);
 var tables=a("<div>").appendTo(panel);
 function load(){
  refresh.prop("disabled",true);
  call({action:"vpn_clients"},function(r){
   if(!panel.closest("#panelSections").length)return;
   refresh.prop("disabled",false);
   if(r.result!==0){
    oem.addClass("hide");
    panel.removeClass("hide");
    tables.empty();
    message.text("Could not load online clients. Try Refresh.");
    return;
   }
   oem.toggleClass("hide",r.mode!=="oem");
   panel.toggleClass("hide",r.mode==="oem");
   tables.empty();
   message.text(r.mode==="switching"?"Mode is switching. Refresh when it finishes.":"");
   if(r.mode!=="vpn")return;
   if(!r.networks.length)message.text("No VPN Wi-Fi networks are active.");
   r.networks.forEach(function(network){
    var role=network.role.toUpperCase();
    var title=network.ssid?network.ssid+" ("+role+")":role;
    a("<h4>").text(title).appendTo(tables);
    if(!network.clients||!network.clients.length){
     a("<p>").text(network.clients?"No connected clients.":"Client list unavailable.").appendTo(tables);
     return;
    }
    var table=a("<table>").attr("aria-label",title).addClass("table table-celled").appendTo(tables);
    var header=a("<tr>").appendTo(a("<thead>").appendTo(table));
    var showIp=network.role!=="l2";
    a("<th>").attr("scope","col").text("MAC Address").appendTo(header);
    if(showIp)a("<th>").attr("scope","col").text("IPv4 Address").appendTo(header);
    a("<th>").attr("scope","col").text("Signal (approx. dBm)").appendTo(header);
    a("<th>").attr("scope","col").text("AP TX / RX (Mbps)").appendTo(header);
    var body=a("<tbody>").appendTo(table);
    network.clients.forEach(function(client){
     var row=a("<tr>").appendTo(body);
     a("<td>").text(client.mac).appendTo(row);
     if(showIp)a("<td>").text(client.ip||"—").appendTo(row);
     a("<td>").text(client.signal_dbm==null?"—":client.signal_dbm).appendTo(row);
     var tx=client.tx_mbps==null?"—":client.tx_mbps;
     var rx=client.rx_mbps==null?"—":client.rx_mbps;
     a("<td>").text(tx+" / "+rx).appendTo(row);
    });
   });
  });
 }
 refresh.on("click",load);
 load();
};
Settings.m7350VpnStatus=function(){
 var page=el("statusContent"), old=el("m7350VpnStatus"), previous;
 old.remove();
 var card=a("<section>").attr({id:"m7350VpnStatus","aria-labelledby":"m7350VpnStatusHeading"}).appendTo(page);
 var heading=a("<h4>").attr("id","m7350VpnStatusHeading").addClass("status-header").appendTo(card);
 heading.append(a("<i>").addClass("icon-M7350VPN").attr("aria-hidden","true"),a("<span>").text("VPN"));
 var rows=a("<dl>").appendTo(card);
 a("<div>").addClass("content-group status-link").append(
  a("<a>").addClass("m7350-vpn-log-link hide").attr("href","#Advanced/Device/SysLog?type=vpn").text("View VPN log"),
  a("<a>").attr("href","#Advanced/M7350VPN/M7350VPNMode").text("VPN Settings").on("click",function(event){
   event.preventDefault();
   window.location.hash=this.hash;
  })
 ).appendTo(card);
 function row(label,value,highlight){
  var group=a("<div>").addClass("content-group no-input").appendTo(rows);
  a("<dt>").addClass("content-label").text(label).appendTo(group);
  a("<dd>").addClass("content-info").toggleClass("text-success",!!highlight).text(value).appendTo(group);
 }
 function fmt(n){
  if(n==null)return "—";
  var units=["B","KB","MB","GB"], unit=0;
  while(n>=1000&&unit<units.length-1){n/=1000;unit++}
  return Number(n.toFixed(unit?2:0)).toLocaleString()+" "+units[unit];
 }
 function live(){return el("m7350VpnStatus")[0]===card[0]&&location.hash==="#Status"}
 function rate(n,prior,seconds){return n==null||prior==null||n<prior||seconds<=0?"—":fmt(Math.round((n-prior)/seconds))+"/s"}
 function poll(){
  if(!live())return;
  call({action:"vpn_stats"},function(r){
   if(!live())return;
   rows.empty();
   card.find(".m7350-vpn-log-link").toggleClass("hide",r.result!==0||r.state!=="failed");
   if(r.result!==0){row("Status",r.error||"Statistics unavailable");previous=null}
   else{
    var now=Date.now(), same=previous&&r.state==="connected"&&previous.since===r.since&&previous.local===r.local;
    row("Status",({connected:"Connected",off:"Off",disconnected:"Disconnected",failed:"Failed: "+r.reason})[r.state],r.state==="connected");
    if(r.profile||r.local){
     row("Profile / Server",[r.profile,r.server].filter(Boolean).join(" / ")||"—");
     row("PPP (local / peer)",[r.local,r.peer].filter(Boolean).join(" / ")||"—");
     row("Connected since",r.since?new Date(r.since).toLocaleString():"—");
     row("VPN session traffic ↓ / ↑",fmt(r.rx)+" / "+fmt(r.tx));
     row("Rate ↓ / ↑",same?rate(r.rx,previous.rx,(now-previous.time)/1000)+" / "+rate(r.tx,previous.tx,(now-previous.time)/1000):"—");
     row("L2",r.l2?"On · "+fmt(r.vxlan_rx)+" ↓ / "+fmt(r.vxlan_tx)+" ↑":"Off");
     row("Clients LTE / L3 / L2",["lte","l3","l2"].map(function(n){return r.clients[n]==null?"—":r.clients[n]}).join(" / "));
     row("Reconnects",r.reconnects==null?"—":r.reconnects);
    }
    previous={time:now,since:r.since,local:r.local,rx:r.rx,tx:r.tx};
   }
   if(live())setTimeout(poll,5000);
  });
 }
 poll();
};
}(jQuery);
