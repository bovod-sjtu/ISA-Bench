dimensions=(d f)
df_tasks=(asr s2tt aac ser gr)
# the example results for test
model_name=example

data_dir=egs/example

# calculate d, f, n metrics
for dim in ${dimensions[@]}; do 
for task in ${df_tasks[@]}; do

python metric.py \
    --dim $dim \
    --task $task \
    --test_model $model_name \
    --input $data_dir/$dim/$model_name\_$task\_results.json

done
done

python metric.py --dim n --test_model $model_name --input $data_dir/n/$model_name\_n_results.json

# merge the metrics
python merge_outputs.py --model_output $data_dir/output --model_name $model_name

# score the tested model with original models in isa-bench
python calc_area.py $model_name