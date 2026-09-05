import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Empty from "../components/Empty.jsx";

const roleColor={ SUPER_ADMIN:"var(--text)", ADMIN:"var(--info)", INSPECTOR:"var(--accent)", OPERATOR:"var(--warn)" };

export default function Users(){
  const [rows,setRows]=useState([]);
  const [q,setQ]=useState("");
  const [role,setRole]=useState("ALL");
  const [err,setErr]=useState("");
  useEffect(()=>{ api("/users").then(setRows).catch(e=>setErr(e.message)); },[]);
  const view=useMemo(()=>{
    let r=[...rows];
    if(q) r=r.filter(u=> `${u.full_name} ${u.email} ${u.role}`.toLowerCase().includes(q.toLowerCase()));
    if(role!=="ALL") r=r.filter(u=>u.role===role);
    return r;
  },[rows,q,role]);
  if(err) return <p className="err">{err}</p>;
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">SYSTEM • USERS</div><h2 className="page-title">Team & roles</h2><p className="page-sub muted">SUPER_ADMIN &gt; ADMIN &gt; INSPECTOR &gt; OPERATOR • JWT gated • <span role="status"><span className="table-num">{view.length}</span> of <span className="table-num">{rows.length}</span> users</span></p></div>
        <div className="filters"><input placeholder="Search name / email" aria-label="Search users" value={q} onChange={e=>setQ(e.target.value)} /><select aria-label="Filter by role" value={role} onChange={e=>setRole(e.target.value)}><option value="ALL">All roles</option><option>SUPER_ADMIN</option><option>ADMIN</option><option>INSPECTOR</option><option>OPERATOR</option></select></div>
      </div>

      <div className="grid-3" style={{marginBottom:12}}>
        {["SUPER_ADMIN","ADMIN","INSPECTOR"].map(r=>(
          <div key={r} className="card" style={{padding:"12px 14px",borderTop:`3px solid ${roleColor[r]}`}}><h4><span className="status-dot" style={{background:roleColor[r]}} aria-hidden="true" /> {r}</h4><div className="n table-num" style={{fontSize:22}}>{rows.filter(x=>x.role===r).length}</div><div className="muted" style={{fontSize:11}}>{r==="SUPER_ADMIN"?"all access": r==="ADMIN"?"command + fleet":"verify / field"}</div></div>
        ))}
      </div>

      <div className="table-wrap">
        <div className="table-toolbar"><span className="muted" style={{fontSize:12}} role="status"><span className="table-num">{view.length}</span> of <span className="table-num">{rows.length}</span> users</span><span className="muted" style={{fontSize:11}}>JWT gated • admin-managed</span></div>
        <div style={{overflow:"auto"}}>
          <table>
            <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
            <tbody>
              {view.map(u=>(
                <tr key={u.id}>
                  <td><div style={{display:"flex",gap:10,alignItems:"center"}}><div className="avatar" aria-hidden="true" style={{width:32,height:32,fontSize:12,background: roleColor[u.role]||"var(--text)"}}>{u.full_name.slice(0,2).toUpperCase()}</div><b>{u.full_name}</b></div></td>
                  <td className="mono" style={{fontSize:12}} title={u.email}>{u.email}</td>
                  <td><span className="tag" title={u.role==="SUPER_ADMIN"?"all access":u.role==="ADMIN"?"command+fleet":u.role==="INSPECTOR"?"verify/field":"sensor/trip"} style={{background:"var(--surface-2)",color:roleColor[u.role],borderColor:"var(--line)",fontSize:11,fontWeight:700}}>{u.role}</span></td>
                  <td><span className="tag real" style={{fontSize:11}}>{u.is_active!==false?"active":"inactive"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {view.length===0 && <Empty icon="○" title="No users match" description={q||role!=="ALL" ? "Try clearing search or role filter" : "No users registered"} actionLabel={(q||role!=="ALL")?"Clear filters":undefined} onAction={(q||role!=="ALL")?()=>{setQ("");setRole("ALL");}:undefined} />}
      </div>
      <p className="muted" style={{fontSize:11,marginTop:8}}>Seed accounts: superadmin / admin / inspector / operator @urbansense.local. Register is admin-gated. Shared demo password is only on the login booth, not here.</p>
    </div>
  );
}
