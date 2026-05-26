"""Debug BEQ output structure."""
import sys; sys.path.insert(0,"src")
import numpy as np, pandas as pd
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import BEQParams

DATASETS = {
    'ipi':('ipi','index',0,{'series':'growth_mom'}),
    'cpi_headline':('cpi_headline','index',1,{'division':'overall'}),
    'cpi_core':('cpi_core','index',1,{'division':'overall'}),
    'ppi':('ppi','index',1,{'series':'abs'}),
    'u_rate':('lfs_month','u_rate',0,{}),
    'p_rate':('lfs_month','p_rate',0,{}),
    'leading':('economic_indicators','leading',1,{}),
    'coincident':('economic_indicators','coincident',1,{}),
    'gdp':('gdp_qtr_real_sa','value',0,{'series':'abs'}),
}
MN=[n for n in DATASETS if n!='gdp']; AN=MN+['gdp']
cache=DataCache(ttl_hours=24); client=OpenDOSMClient(); filtered={}
for name,(did,col,tcode,filters) in DATASETS.items():
    df=cache.get(did)
    if df is None: df=client.fetch(did,limit=20000)
    if df is None: continue
    df=df.copy()
    for fc,fv in filters.items():
        if fc in df.columns: df=df[df[fc]==fv]
    if col not in df.columns: continue
    df=df[['date',col]].dropna().rename(columns={col:name})
    df['date']=pd.to_datetime(df['date'])
    df=df.sort_values('date').drop_duplicates('date')
    filtered[name]=df
if 'ipi' in filtered: filtered['ipi']['ipi']=filtered['ipi']['ipi']/100.0
gdp_df=filtered['gdp'].copy().sort_values('date')
gv=gdp_df['gdp'].values; gq=np.full(len(gv),np.nan)
for i in range(1,len(gv)):
    if gv[i-1]>0: gq[i]=(gv[i]-gv[i-1])/gv[i-1]
gdp_df['gdp']=gq; gdp_df=gdp_df.dropna(subset=['gdp']); filtered['gdp']=gdp_df
md=[df['date'].min() for df in filtered.values()]; Mx=[df['date'].max() for df in filtered.values()]
sd=max(md); ed=max(Mx)
datet=generate_dates(sd.year,sd.month,ed.year,ed.month); T=len(datet)
X=np.full((T,len(MN)+1),np.nan)
for j,name in enumerate(MN):
    df=filtered[name]
    for _,row in df.iterrows():
        y,m=row['date'].year,row['date'].month
        idx=np.where((datet[:,0]==y)&(datet[:,1]==m))[0]
        if len(idx)>0: X[idx[0],j]=row[name]
gdp_df_q=filtered['gdp']
for _,row in gdp_df_q.iterrows():
    y,m=row['date'].year,row['date'].month
    qem=((m-1)//3)*3+3
    idx=np.where((datet[:,0]==y)&(datet[:,1]==qem))[0]
    if len(idx)>0: X[idx[0],-1]=row['gdp']
X_trans=X.copy()
for j,name in enumerate(AN):
    tcode=DATASETS[name][2]; freq='quarterly' if name=='gdp' else 'monthly'
    X_trans[:,j]=transform_series(X[:,j].copy(),tcode,freq)
mu=np.nanmean(X_trans,axis=0); sigma=np.nanstd(X_trans,axis=0); sigma[sigma<1e-10]=1.0
X_std=(X_trans-mu)/sigma
ff=np.where(~np.all(np.isnan(X_std),axis=1))[0][0]
X_est=X_std[ff:]; datet_est=datet[ff:]
client.close()

beq=BEQ(BEQParams(lagM=1,lagQ=1,lagY=1,type=901))
res=beq.fit(X_est, datet_est, AN)

print(f"X_sm shape: {res.X_sm.shape}")
print(f"Y_fcst shape: {res.Y_fcst.shape}")
print()

# Last 12 rows
print("Last 12 months GDP column:")
for i in range(max(0, len(datet_est)-12), len(datet_est)):
    y, m = int(datet_est[i,0]), int(datet_est[i,1])
    val = res.X_sm[i, -1]
    marker = " <-- Q-end" if m % 3 == 0 else ""
    print(f"  {y}-{m:02d}: {val:+.6f}{marker}")

# Last quarter-end with valid GDP
print()
for i in range(len(datet_est)-1, -1, -1):
    if int(datet_est[i,1]) % 3 == 0:
        y, m = int(datet_est[i,0]), int(datet_est[i,1])
        val = res.X_sm[i, -1]
        if not np.isnan(val):
            nw = val * sigma[-1] + mu[-1]
            print(f"Last Q-end GDP: {y}-{m:02d} = {nw*100:+.2f}% (std={val:.6f})")
            break
