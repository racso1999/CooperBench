import pandas as pd

# build the data frame
df = pd.read_csv('all_runs.csv')
flash_msg = df[df['arm'] == 'flash_msg']
flash_solo = df[df['arm'] == 'flash_solo']


# remove typst_task/6554
flash_msg = flash_msg[~((flash_msg['repo'] == 'typst_task') & (flash_msg['task_id'] == 6554))][['task_id', 'pair', 'repeat', 'both_passed', 'total_cost']].sort_values(['task_id', 'pair', 'repeat'])
flash_solo = flash_solo[~((flash_solo['repo'] == 'typst_task') & (flash_solo['task_id'] == 6554))][['task_id', 'pair', 'repeat', 'both_passed', 'total_cost']].sort_values(['task_id', 'pair', 'repeat'])


# passrates
flash_msg_rates = flash_msg.groupby(['task_id', 'pair'])['both_passed'].mean().reset_index()
flash_msg_rates = flash_msg_rates.rename(columns={'both_passed': 'pass_rate'})

flash_solo_rates = flash_solo.groupby(['task_id', 'pair'])['both_passed'].mean().reset_index()
flash_solo_rates = flash_solo_rates.rename(columns={'both_passed': 'pass_rate'})

flash_msg_rates['pass_rate'] = flash_msg_rates['pass_rate'].astype(float)
flash_solo_rates['pass_rate'] = flash_solo_rates['pass_rate'].astype(float)

print('flash_solo overall pass rate:', flash_solo_rates['pass_rate'].mean())
print('flash_msg overall pass rate:', flash_msg_rates['pass_rate'].mean())

merged = flash_solo_rates.merge(flash_msg_rates, on=['task_id', 'pair'], suffixes=('_solo', '_msg'))

from scipy.stats import wilcoxon
stat, p_value = wilcoxon(merged['pass_rate_solo'], merged['pass_rate_msg'])
print('Wilcoxon statistic:', stat)
print('p-value:', p_value)


# --- cost-normalized comparison (passes per dollar spent) ---

flash_msg_eff = flash_msg.groupby(['task_id', 'pair']).agg(passed=('both_passed', 'sum'), cost=('total_cost', 'sum')).reset_index()
flash_solo_eff = flash_solo.groupby(['task_id', 'pair']).agg(passed=('both_passed', 'sum'), cost=('total_cost', 'sum')).reset_index()

flash_msg_eff['passed'] = flash_msg_eff['passed'].astype(float)
flash_solo_eff['passed'] = flash_solo_eff['passed'].astype(float)

flash_msg_eff['passes_per_dollar'] = flash_msg_eff['passed'] / flash_msg_eff['cost']
flash_solo_eff['passes_per_dollar'] = flash_solo_eff['passed'] / flash_solo_eff['cost']

solo_ppd = flash_solo_eff['passed'].sum() / flash_solo_eff['cost'].sum()
msg_ppd = flash_msg_eff['passed'].sum() / flash_msg_eff['cost'].sum()
print('flash_solo passes per dollar:', solo_ppd)
print('flash_msg passes per dollar:', msg_ppd)

merged_eff = flash_solo_eff.merge(flash_msg_eff, on=['task_id', 'pair'], suffixes=('_solo', '_msg'))
stat2, p_value2 = wilcoxon(merged_eff['passes_per_dollar_solo'], merged_eff['passes_per_dollar_msg'])
print('Wilcoxon statistic (cost-normalized):', stat2)
print('p-value (cost-normalized):', p_value2)


# --- combined overlay chart: pass rate vs cost-normalized, side by side ---
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['font.size'] = 9

solo_pass_rate_mean = flash_solo_rates['pass_rate'].mean()
msg_pass_rate_mean = flash_msg_rates['pass_rate'].mean()

# same hue family, slightly different shade per group so the two groups read as visually distinct
pass_solo_color = '#4C72B0'   # blue
pass_msg_color = '#DD8452'    # orange
cost_solo_color = '#7A9FC9'   # lighter blue
cost_msg_color = '#E8A06D'    # lighter orange

fig, ax1 = plt.subplots()
ax2 = ax1.twinx()

pos1, pos2 = 0, 0.8
width = 0.7

# group 1 (pass rate) at pos1: solo behind, messaging overlaid on top, same width
ax1.bar([pos1], [solo_pass_rate_mean], width=width, color=pass_solo_color, edgecolor='black', linewidth=0.4, label='Solo')
ax1.bar([pos1], [msg_pass_rate_mean], width=width, color=pass_msg_color, edgecolor='black', linewidth=0.4, label='Messaging')
ax1.set_ylim(0, solo_pass_rate_mean)
ax1.set_ylabel('Pass rate')
ax1.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0))

# group 2 (cost-normalized) at pos2: same overlay pattern, same width
ax2.bar([pos2], [solo_ppd], width=width, color=cost_solo_color, edgecolor='black', linewidth=0.4)
ax2.bar([pos2], [msg_ppd], width=width, color=cost_msg_color, edgecolor='black', linewidth=0.4)
ax2.set_ylim(0, solo_ppd)
ax2.set_ylabel('Passes per dollar')

ax1.set_xticks([pos1, pos2])
ax1.set_xticklabels(['Pass rate', 'Cost-normalized'])
ax1.set_xlim(pos1 - 0.5, pos2 + 0.5)
ax1.set_title('Coordination Gap: Raw Pass Rate vs Cost-Normalized')

ax1.spines['top'].set_visible(False)
ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)

plt.tight_layout()
plt.savefig('overlay_comparison.png', dpi=150)
plt.show()