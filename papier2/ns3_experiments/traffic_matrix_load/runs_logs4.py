#[tcp_flow_id],[now_in_ns],[progress_byte/cwnd_byte/rtt_ns]
"""
README
Plot results obtained when enabling logs in the ns3 simulation 
to see which commodity is involved, refer to hypatia/papier2/satellite_networks_state/input_data/commodites.txt
visualizations of the path can be found in the pdf files hypatia/papier2/satgenpy_analysis/data/*/*/manual/pdf
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


interdoss="/logs_ns3/"#tcp_flow"[id]_{progress, cwnd, rtt}.csv`
algorithm_styles = [
	("algorithm_free_one_only_over_isls", "1-nearest", "g"),
	("algorithm_free_one_only_over_isls3", "3-nearest", "b"),
	("algorithm_free_one_only_over_isls5", "5-nearest", "r"),
]

dossiers = []
for algorithm_name, legend_label, colour in algorithm_styles:
	for doss in sorted(os.listdir("runs")):
		runsdoss = "runs/" + doss
		if not os.path.isdir(runsdoss):
			continue
		if '_120s' not in doss or '10' not in doss or '_with_tcp_' not in doss:
			continue
		if doss.endswith(algorithm_name):
			dossiers.append((runsdoss, legend_label, colour))
			break

fig,axes=plt.subplots(3,1, figsize=(16,9), dpi=80, facecolor="w", edgecolor='k')
i=0
for doss, legend_label, colour in dossiers:
	fics=sorted([fic for fic in os.listdir(doss+interdoss) if os.path.isfile(doss+interdoss+fic) and "tcp_flow_" in fic])
	if fics:
		print(doss)
		ident=fics[0].split('_')[2]
		
		with open(doss+interdoss+"tcp_flow_"+ident+"_cwnd.csv","r") as fcwnd,\
			open(doss+interdoss+"tcp_flow_"+ident+"_progress.csv","r") as fprog,\
			open(doss+interdoss+"tcp_flow_"+ident+"_rtt.csv","r") as frtt:
			cwnds=fcwnd.readlines()
			progres=fprog.readlines()
			rtts=frtt.readlines()

		t_cwnds=[int(line.split(',')[1])/10**9 for line in cwnds]
		data_cwnds=[int(line.strip().split(',')[-1]) for line in cwnds]
		fig.suptitle('commodity id:'+cwnds[0].split(',')[0]+" from "+doss)
		#axes[0].title('cwnds id'+cwnds[0].split(',')[0]+" "+doss)
		axes[0].set_xlabel("temps simu(s)")
		axes[0].set_ylabel("cwnd (bytes)")
		axes[0].plot(t_cwnds,data_cwnds,colour, label=legend_label)
		axes[0].legend(loc="upper left")

		t_rtts=[int(line.split(',')[1])/10**9 for line in rtts]
		data_rtts=[int(line.strip().split(',')[-1])/10**6 for line in rtts]
		#axes[1].title('RTTs id'+cwnds[0].split(',')[0]+" "+doss)
		axes[1].set_xlabel("temps simu(s)")
		axes[1].set_ylabel("rtts (ms)")
		axes[1].plot(t_rtts,data_rtts,colour, label=legend_label)
		axes[1].legend(loc="upper left")

		t_prgs=[int(line.split(',')[1])/10**9 for line in progres]
		data_prgs=[int(line.strip().split(',')[-1]) for line in progres]
		#axes[2].title('progres id'+cwnds[0].split(',')[0]+" "+doss)
		axes[2].set_xlabel("temps simu(s)")
		axes[2].set_ylabel("progres (bytes)")
		axes[2].plot(t_prgs,data_prgs,colour, label=legend_label)
		axes[2].legend(loc="upper left")
		i+=1

if i == 0:
	print("Aucune donnee tcp_flow_*.csv trouvee dans runs/*/logs_ns3")
	exit(0)

out_dir = "pdf"
os.makedirs(out_dir, exist_ok=True)
out_pdf = os.path.join(out_dir, "runs_logs4_tcp_overlay_120s_10mbps.pdf")
out_png = os.path.join(out_dir, "runs_logs4_tcp_overlay_120s_10mbps.png")
fig.tight_layout()
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=180)
print("Saved:", out_pdf)
print("Saved:", out_png)

# Keep interactive display only when a display is available.
if os.environ.get("DISPLAY"):
	plt.show()
else:
	plt.close(fig)
