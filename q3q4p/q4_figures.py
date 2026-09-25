from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import q3_figures as common

ROOT = Path(__file__).resolve().parent
Q4_PATH = ROOT / 'inputs' / '问题四任务分区与资源配置结果.json'
GROUP_COLORS = ['#3E719B', '#409E99', '#D88174']
SCENARIO_COLORS = ['#4E79A7', '#62B7B4', '#D4AD43', '#E88982']
BALANCED_FIXED = '25%均衡约束下缺口最小方案'
BALANCED_REASSIGNED = '25%均衡约束下组内重派缺口最小方案'
UNBALANCED_REASSIGNED = '组内重派缺口最小方案'


def load_data():
    return json.loads(Q4_PATH.read_text(encoding='utf-8'))


def flowchart():
    fig, ax = plt.subplots(figsize=(17.6, 7.1))
    ax.set_xlim(0, 25)
    ax.set_ylim(0, 10)
    ax.axis('off')
    columns = [
        ('任务与分区', [('固定第三问路线、时刻\n机型与通信关系', 'white'),
                        ('合并共同运输或中继任务\n得到7个不可拆分单元', common.CYAN),
                        ('枚举非空、无序分组\n两组63种；三组301种', common.YELLOW)]),
        ('固定编号核算', [('每组统计原执行设备\n及能源组件编号', 'white'),
                          ('同编号若出现在不同组\n各组分别配置实物', common.CYAN),
                          ('汇总各类型需求\n与现有库存比较', common.GREEN)]),
        ('组内重派核算', [('分别建立各类资源\n飞行、充电或周转占用区间', 'white'),
                          ('按开始时刻安排同类设备\n已释放设备优先复用', common.CYAN),
                          ('求各组最少需求\n汇总各类型库存缺口', common.GREEN)]),
        ('方案选择', [('两种口径分别选取\n资源缺口最小分区', common.PINK),
                    ('附加货箱与架次均衡条件\n比较25%条件下的方案', common.YELLOW),
                    ('同缺口时依次比较\n货箱、架次、能耗、时长极差', 'white')]),
        ('检查与比较', [('核对任务唯一归属\n及分组能耗之和', common.CYAN),
                        ('列出两组、三组分区\n资源需求与库存缺口', common.BLUE),
                        ('比较10%—40%均衡阈值\n对应的最小资源缺口', common.YELLOW)]),
    ]
    for i, (title, steps) in enumerate(columns):
        x = .3 + i*5
        common.flow_group(ax, x, 1.3, 4.4, 8, title)
        for j, (label, fill) in enumerate(steps):
            y = [6.9, 4.6, 2.3][j]
            common.flow_box(ax, x+.38, y, 3.64, 1.05, label, fill=fill,
                            fs=10, color='white' if fill == common.BLUE else common.INK)
            if j:
                common.flow_arrow(ax, [(x+2.2, y+2.3), (x+2.2, y+1.05)])
        if i < 4:
            common.flow_arrow(ax, [(x+4.02, 2.825), (x+4.68, 2.825),
                                   (x+4.68, 7.425), (x+5.38, 7.425)])
    ax.text(12.5, .55, '固定编号与组内重派为两种分别核算的口径；25%均衡条件为附加比较，不是题目硬约束。',
            ha='center', fontsize=10, color=common.MUTED)
    common.save(fig, '图15_第四问任务分区与资源配置流程图')


def terrain_background():
    origin, services = common.load_nodes()
    dem, lat, lon = common.load_dem()
    rows = (lat >= min(services['纬度'].min(), origin['纬度'])-.018) & (lat <= max(services['纬度'].max(), origin['纬度'])+.018)
    cols = (lon >= min(services['经度'].min(), origin['经度'])-.020) & (lon <= max(services['经度'].max(), origin['经度'])+.020)
    terrain = dem[np.ix_(rows, cols)]
    x, _ = common.local_xy(lon[cols], np.zeros(sum(cols))+origin['纬度'], origin['经度'], origin['纬度'])
    _, y = common.local_xy(np.zeros(sum(rows))+origin['经度'], lat[rows], origin['经度'], origin['纬度'])
    cmap = LinearSegmentedColormap.from_list('terrain', ['#214f78','#3f7da3','#72abc1','#add1c8','#e6dfaa','#f3d793'])
    norm = Normalize(*np.nanpercentile(terrain, [1.5, 98.5]))
    rgb = LightSource(315, 42).shade(terrain, cmap=cmap, norm=norm, vert_exag=.65, blend_mode='soft')
    # A light terrain background keeps group membership prominent without changing the elevation scale.
    rgb[:, :, :3] = .78*rgb[:, :, :3] + .22
    return origin, services, terrain, x, y, rgb, cmap, norm


def partition_map(q4, count, balanced=True):
    origin, services, terrain, x, y, rgb, cmap, norm = terrain_background()
    plan = q4['分区方案'][str(count)][BALANCED_REASSIGNED if balanced else UNBALANCED_REASSIGNED]
    assigned = [s for g in plan['任务组'] for s in g['服务区']]
    memberships = {s: i for i, g in enumerate(plan['任务组']) for s in g['服务区']}
    assert len(assigned) == len(memberships) == 15
    assert set(assigned) == set(services['编号'])
    assert sum(g['货箱数'] for g in plan['任务组']) == 80
    assert sum(g['运输架次']+g['中继架次'] for g in plan['任务组']) == 25
    assert sum(plan['组内重派资源缺口'].values()) == plan['组内重派缺口合计']
    fig, ax = plt.subplots(figsize=(11.4, 10.1))
    fig.subplots_adjust(left=.10, right=.88, top=.84, bottom=.15)
    ax.imshow(rgb, extent=[x.min(), x.max(), y.min(), y.max()], origin='lower', aspect='equal')
    ax.contour(x, y, terrain, levels=np.arange(100, 1201, 100), colors='white', alpha=.3, linewidths=.35)
    offsets = {'S001':(9,9), 'S002':(9,8), 'S003':(-9,9), 'S004':(9,9),
               'S005':(9,8), 'S006':(-9,-14), 'S007':(-9,8), 'S008':(-9,8),
               'S009':(9,8), 'S010':(9,-15), 'S011':(-9,8), 'S012':(9,8),
               'S013':(9,9), 'S014':(9,-15), 'S015':(-9,9)}
    for _, row in services.iterrows():
        px, py = common.local_xy(row['经度'], row['纬度'], origin['经度'], origin['纬度'])
        i = memberships[row['编号']]
        color = GROUP_COLORS[i]
        ax.scatter([px], [py], s=115, c=color, marker=['o','s','^'][i], edgecolor='white', linewidth=1.2, zorder=5)
        dx, dy = offsets[row['编号']]
        ax.annotate(row['编号'], (px,py), xytext=(dx,dy), textcoords='offset points',
                    ha='left' if dx > 0 else 'right', va='center', fontsize=10, weight='bold',
                    bbox=dict(boxstyle='round,pad=.18', fc='white', ec='none', alpha=.9), zorder=6)
    ax.scatter([0], [0], s=235, c='#941818', marker='*', edgecolor='white', linewidth=1, zorder=7)
    ax.annotate('O01', (0,0), xytext=(10,-15), textcoords='offset points', color='#781616',
                weight='bold', bbox=dict(fc='white', ec='none', alpha=.85), zorder=8)
    ax.set_xlim(x.min(), x.max()); ax.set_ylim(y.min(), y.max())
    ax.set_xlabel('东西方向 / km（以O01为原点）'); ax.set_ylabel('南北方向 / km（以O01为原点）')
    ax.grid(color='white', alpha=.32, linewidth=.6)
    title = f'第四问{count}组服务区分配方案' if balanced else f'第四问{count}组资源缺口最小分区（不加均衡条件）'
    fig.suptitle(title, x=.10, ha='left', y=.955, fontsize=17, weight='bold')
    subtitle = ('货箱与联合架次数偏离组均值不超过25%；允许组内重派同类型资源。' if balanced else
                f"允许组内重派同类型资源；最小资源缺口为{plan['组内重派缺口合计']}件。")
    fig.text(.10,.916,subtitle, fontsize=10, color=common.MUTED)
    labels = [f"{g['任务组']}：{g['货箱数']}箱 / {g['运输架次']+g['中继架次']}架次" for g in plan['任务组']]
    handles = [Line2D([0],[0],marker=['o','s','^'][i],ls='', color=GROUP_COLORS[i],markersize=9,label=t) for i,t in enumerate(labels)]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.095,.894), ncol=count, frameon=False, fontsize=10)
    cax = fig.add_axes([.905,.24,.018,.48])
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm,cmap=cmap), cax=cax)
    cb.set_label('地面高程 / m')
    fig.text(.10,.065, '颜色与点形仅表示任务组归属，不表示行政边界或连续地理分区。', color=common.MUTED, fontsize=9.5)
    if not balanced:
        fig.text(.10,.035, f'与图{14+count}的25%均衡方案比较；任务组编号仅在各自方案内有效。', color=common.MUTED, fontsize=9.5)
    name = (f'图{14+count}_第四问{count}组服务区分区地图' if balanced else
            f'图{18+count}_第四问{count}组无均衡条件分区地图')
    common.save(fig, name)


def deficits(q4):
    labels, values = [], []
    keys = ['A型运输无人机','B型运输无人机','C型运输无人机','B型共享电池','C型共享电池','中继无人机']
    colors = ['#4E79A7','#62B7B4','#E9C75B','#A9DDE0','#F3DEA0','#E88982']
    hatches = ['', '', '', '///', '///', '']
    for count in [2,3]:
        for key, desc, field in [(BALANCED_FIXED,'固定编号','资源缺口'), (BALANCED_REASSIGNED,'组内重派','组内重派资源缺口')]:
            plan = q4['分区方案'][str(count)][key]
            labels.append(f'{count}组 · {desc}')
            values.append([plan[field][k] for k in keys])
    values = np.asarray(values)
    assert values.sum(axis=1).tolist() == [8,4,14,13]
    fig, ax = plt.subplots(figsize=(12.8,6.9))
    fig.subplots_adjust(left=.17,right=.96,bottom=.22,top=.78)
    y = np.array([3.2,2.2,.7,-.3]); left = np.zeros(4)
    for j,k in enumerate(keys):
        ax.barh(y,values[:,j],left=left,height=.66,color=colors[j],edgecolor='white',linewidth=1.1,hatch=hatches[j],label=k)
        for i,v in enumerate(values[:,j]):
            if v:
                ax.text(left[i]+v/2,y[i],str(v),ha='center',va='center',fontsize=12,color='white' if j == 0 else common.INK,weight='bold')
        left += values[:,j]
    for yy,total in zip(y,left):
        ax.text(total+.2,yy,f'{int(total)}件',va='center',fontsize=12,weight='bold')
    ax.set_yticks(y); ax.set_yticklabels(labels,fontsize=11)
    ax.set_xlim(0,16); ax.set_xlabel('资源缺口 / 件')
    ax.grid(axis='x',color=common.GRID,linewidth=.8); ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    fig.suptitle('25%均衡条件下的资源缺口构成',x=.17,y=.96,ha='left',fontsize=17,weight='bold')
    fig.text(.17,.90,'各口径分别选择缺口最小分区；条内数字为对应资源缺少数量。',fontsize=10,color=common.MUTED)
    ax.legend(loc='upper left',bbox_to_anchor=(0,1.16),ncol=3,frameon=False,fontsize=9.5)
    fig.text(.17,.09,'A型共享电池与中继能源组件在四种方案中均无缺口。',fontsize=9.5,color=common.MUTED)
    fig.text(.17,.05,'两组固定原分区时，组内重派将缺口由8件降至6件；重新选取分区后最小为4件。',fontsize=9.5,color=common.MUTED)
    common.save(fig,'图18_第四问资源缺口构成')


def waterfall(q4):
    series = []
    for count in [2,3]:
        rows = q4['分区方案'][str(count)]['均衡阈值敏感性']
        for field, suffix in [('固定编号最小缺口','固定编号'),('组内重派最小缺口','组内重派')]:
            series.append((f'{count}组 · {suffix}',np.array([r['允许偏离均值']*100 for r in rows]),
                           np.array([r[field] if r[field] is not None else np.nan for r in rows],dtype=float)))
    fig = plt.figure(figsize=(13.2,9.2))
    ax = fig.add_subplot(111,projection='3d')
    fig.subplots_adjust(left=.02,right=.89,bottom=.12,top=.88)
    for i,(label,x,z) in enumerate(series):
        valid = np.isfinite(z); xx=x[valid]; zz=z[valid]
        verts=[(xx[0],i,0)]+[(a,i,b) for a,b in zip(xx,zz)]+[(xx[-1],i,0)]
        poly=Poly3DCollection([verts],facecolor=SCENARIO_COLORS[i],alpha=.22,edgecolor='none')
        ax.add_collection3d(poly)
        ax.plot(xx,np.zeros(len(xx))+i,zz,color=SCENARIO_COLORS[i],lw=2.6,marker='o',ms=5)
        # All five points carry observed scenario values; connecting lines are visual guides only.
        for a,b in zip(xx,zz):
            if a in (25,40):
                ax.text(a,i,b+.55,str(int(b)),ha='center',fontsize=10,color=common.INK)
        ax.plot([25,25],[i,i],[0,zz[np.where(xx==25)[0][0]]],color='#606A72',ls=':',lw=.8,alpha=.7)
    ax.set_xlim(8,42); ax.set_ylim(-.35,3.55); ax.set_zlim(0,17)
    ax.set_xticks([10,20,25,30,40]); ax.set_xticklabels(['10%','20%','25%','30%','40%'])
    ax.set_yticks(range(4)); ax.set_yticklabels([s[0] for s in series],fontsize=9)
    ax.set_xlabel('允许偏离组均值',labelpad=10)
    ax.set_zlabel('最小资源缺口 / 件',labelpad=9)
    ax.view_init(elev=26,azim=-57); ax.set_box_aspect((1.5,1.2,1))
    for axis in [ax.xaxis,ax.yaxis,ax.zaxis]:
        axis.pane.set_facecolor((.97,.98,.985,.5))
        axis._axinfo['grid']['color']=(.75,.80,.83,.42)
    fig.suptitle('均衡要求与最小资源缺口的关系',x=.10,y=.965,ha='left',fontsize=17,weight='bold')
    fig.text(.10,.92,'分层表示四种方案；虚线标出25%情景。三组10%情景无合法分区，曲线从20%起绘制。',fontsize=10,color=common.MUTED)
    fig.text(.10,.045,'仅约束货箱数和联合架次数；三组10%情景无合法分区，未按零缺口处理。连线不代表未计算阈值的结果。',fontsize=9,color=common.MUTED)
    common.save(fig,'图19_第四问均衡阈值与资源缺口三维瀑布图')


def feasible_waterfall(q4):
    """Show counts of feasible unordered partitions, not resource deficits."""
    fig = plt.figure(figsize=(13.2,9.2))
    ax = fig.add_subplot(111, projection='3d')
    fig.subplots_adjust(left=.02,right=.88,bottom=.14,top=.86)
    for i, count in enumerate([2,3]):
        rows = q4['分区方案'][str(count)]['均衡阈值敏感性']
        x = np.array([r['允许偏离均值']*100 for r in rows])
        z = np.array([r['可行分区数'] for r in rows])
        assert np.all(np.diff(z) >= 0)
        assert np.all(z <= q4['分区方案'][str(count)]['可行分区枚举数'])
        assert z[np.flatnonzero(np.isclose(x,25))[0]] == q4['分区方案'][str(count)]['25%均衡约束可行方案数']
        color = SCENARIO_COLORS[i]
        verts = [(x[0],i,0)] + [(a,i,b) for a,b in zip(x,z)] + [(x[-1],i,0)]
        ax.add_collection3d(Poly3DCollection([verts],facecolor=color,alpha=.20,edgecolor='none'))
        ax.plot(x,np.full(len(x),i),z,color=color,lw=2.6,marker='o',ms=6)
        for a,b in zip(x,z):
            # The back layer's zero projects close to the front layer's 16.
            # Raise its label so the two values remain separately readable.
            offset = 5.0 if b == 0 else 1.5
            ax.text(a,i,b+offset,str(int(b)),ha='center',fontsize=11,color=common.INK)
        v = z[np.flatnonzero(np.isclose(x,25))[0]]
        ax.plot([25,25],[i,i],[0,v],color='#606A72',ls=':',lw=.9,alpha=.8)
    ax.set_xlim(8,42); ax.set_ylim(-.3,1.4); ax.set_zlim(0,42)
    ax.set_xticks([10,20,25,30,40]); ax.set_xticklabels(['10%','20%','25%','30%','40%'])
    ax.set_yticks([0,1]); ax.set_yticklabels(['两组分区','三组分区'],fontsize=11)
    ax.set_zticks([0,10,20,30,40])
    ax.set_xlabel('允许偏离组均值',labelpad=12)
    ax.set_zlabel('可行分区数量 / 种',labelpad=12)
    ax.view_init(elev=28,azim=-57); ax.set_box_aspect((1.5,.95,1))
    for axis in [ax.xaxis,ax.yaxis,ax.zaxis]:
        axis.pane.set_facecolor((.97,.98,.985,.5))
        axis._axinfo['grid']['color']=(.75,.80,.83,.42)
    fig.suptitle('均衡要求与可行分区数量的关系',x=.10,y=.965,ha='left',fontsize=17,weight='bold')
    fig.text(.10,.92,'两层分别表示两组、三组；点旁数字为可行分区数，虚线标出25%情景。',fontsize=10,color=common.MUTED)
    fig.text(.10,.075,'可行指货箱数与联合架次数满足均衡条件，不表示现有库存足够；三组10%处为0种。',fontsize=9.5,color=common.MUTED)
    fig.text(.10,.043,'非空、无序分区共枚举两组63种、三组301种。连线仅用于比较已计算情景。',fontsize=9.5,color=common.MUTED)
    common.save(fig,'图22_第四问均衡阈值与可行分区数三维瀑布图')


def supplementary_figures(q4):
    partition_map(q4,2,balanced=False)
    partition_map(q4,3,balanced=False)
    feasible_waterfall(q4)


def latex_table(caption,label,columns,rows,note):
    nl='\n'; row_end=r' \\'
    lines=[r'\begin{table}[htbp]',r'\centering',r'\small',r'\caption{'+caption+'}',r'\label{'+label+'}',
           r'\setlength{\tabcolsep}{6pt}',r'\renewcommand{\arraystretch}{1.2}',
           r'\begin{tabular}{'+'l'*2+'r'*(len(columns)-2)+'}',r'\toprule',
           ' & '.join(columns)+row_end,r'\midrule']
    lines += [' & '.join(map(str,row))+row_end for row in rows]
    lines += [r'\bottomrule',r'\end{tabular}',r'\par\smallskip',r'\begin{minipage}{0.98\linewidth}',
              r'\footnotesize 注：'+note,r'\end{minipage}',r'\end{table}']
    return nl.join(lines)+nl


def write_tables(q3,q4):
    table_dir=ROOT/'tables'; table_dir.mkdir(exist_ok=True)
    rows=[]
    for n in [2,3]:
        plan=q4['分区方案'][str(n)][BALANCED_REASSIGNED]
        assert sum(g['货箱数'] for g in plan['任务组'])==80
        assert sum(g['运输架次']+g['中继架次'] for g in plan['任务组'])==25
        energy=sum(g['运输能耗_kWh']+g['中继能耗_kWh'] for g in plan['任务组'])
        assert abs(energy-q3['指标汇总']['总能耗_kWh'])<1e-8
        for g in plan['任务组']:
            rows.append([f'{n}组',g['任务组'],g['货箱数'],g['运输架次']+g['中继架次'],
                         f"{g['运输能耗_kWh']+g['中继能耗_kWh']:.2f}",f"{g['任务占用时长_s']/3600:.2f}"])
    q4_tex=latex_table('两组与三组方案的工作量比较','tab:q4-workload',
                       ['分组规模','任务组','货箱/箱','联合架次','能耗/kWh','任务占用时长/h'],rows,
                       r'采用货箱数和联合架次数偏离组均值不超过25\%时的组内重派方案。任务占用时长为各运输任务开始至返航、中继任务准备开始至返航时长之和，允许任务并行；它不等于联合任务完成时间。')
    (table_dir/'第四问工作量对照表.tex').write_text(q4_tex,encoding='utf-8')
    rows=[]
    for m in q3['中继架次']:
        rows.append([m['中继架次'],m['中继无人机']+' / '+m['服务区域'],
                     f"{m['建链完成_服务开始_s']:.2f}",f"{m['服务结束_s']:.2f}",f"{m['返回O01_s']:.2f}",
                     f"{m['总能耗_kWh']:.4f}",f"{100*m['返航SOC']:.2f}"])
    relay=latex_table('第三问中继架次安排','tab:q3-relay',
                      ['架次','无人机/区域','建链完成/s','服务结束/s','返航/s','能耗/kWh',r'SOC/\%'],rows,
                      '建链完成后开始提供通信服务。能耗包括往返飞行以及建链、通信服务期间的悬停能耗。')
    rows=[]
    for s in q3['通信保障汇总']:
        rows.append([s['服务区域'],s['中继架次'],s['直连缺口样本数'],f"{s['最小接入裕量_dB']:.3f}",
                     f"{s['回传裕量_dB']:.3f}",f"{s['最小双段裕量_dB']:.3f}",s['中断样本数']])
    margins=latex_table('第三问分区域通信检查结果','tab:q3-coverage',
                       ['区域','中继架次','缺口样本数','接入裕量/dB','回传裕量/dB','双段裕量/dB','中断数'],rows,
                       '接入裕量与双段裕量取区域内样本最小值。零中断结论针对逐秒检查及边界加密样本，不是连续时间的解析证明。')
    (table_dir/'第三问结果表格.tex').write_text(relay+'\n'+margins,encoding='utf-8')
    preview=r'''\documentclass[UTF8,a4paper,11pt]{ctexart}
\usepackage[margin=18mm]{geometry}
\usepackage{booktabs}
\pagestyle{empty}
\begin{document}
\input{第三问结果表格.tex}
\clearpage
\input{第四问工作量对照表.tex}
\end{document}
'''
    (table_dir/'tables_preview.tex').write_text(preview,encoding='utf-8')


def main():
    common.setup_style()
    data=load_data()
    flowchart()
    partition_map(data,2)
    partition_map(data,3)
    deficits(data)
    waterfall(data)
    supplementary_figures(data)
    write_tables(common.load_json(common.Q3_PATH),data)


if __name__ == '__main__':
    main()
