import argparse
import os

def process_metrics(dim, task, input_file, output_file):
    # Placeholder for the actual metric processing logic
    print(f"Processing metrics for dim={dim}, task={task}, input={input_file}, output={output_file}")
    # Here you would add the code to read the input file, compute metrics, and write to the output file
    if dim == 'd' :
        if task == 'asr':
            os.system(f"python metric/d/compute_if_wer.py {input_file} > {output_file}")
        elif task == 'aac':
            os.system(f"python metric/d/compute_if_aac.py {input_file} > {output_file}")
        elif task == 's2tt':
            os.system(f"python metric/d/compute_if_bleu.py {input_file} > {output_file}")
        elif task == 'gr' or task == 'ser':
            os.system(f"python metric/d/compute_if_acc.py {input_file} > {output_file}")
    elif dim == 'f' :
        if task == 'asr':
            os.system(f"python metric/f/compute_if_wer.py {input_file} > {output_file}")
        elif task == 'aac':
            os.system(f"python metric/f/compute_if_aac.py {input_file} > {output_file}")
        elif task == 's2tt':
            os.system(f"python metric/f/compute_if_bleu.py {input_file} > {output_file}")
        elif task == 'gr' or task == 'ser':
            os.system(f"python metric/f/compute_if_acc.py {input_file} > {output_file}")
    elif dim == 'n' :
        os.system(f"python metric/n/compute_ifr_metrics.py {input_file} > {output_file}")
        

def main():
    parser = argparse.ArgumentParser(description="Process metrics based on dimension and task.")
    parser.add_argument("--dim", required=True, choices=["d", "f", "n"], help="Dimension: d, f, or n")
    parser.add_argument("--task", choices=["asr", "aac", "s2tt", "gr", "ser"], help="Task type")
    parser.add_argument("--test_model", required=True, help="The tested model name")
    parser.add_argument("--input", required=True, help="Input JSON file")
    parser.add_argument("--output", help="Output JSON file, default will be output/{dim}/{task}/input_base_{dim}_{task}_metric.json")

    args = parser.parse_args()

    # Validate input file
    if not os.path.isfile(args.input):
        raise FileNotFoundError(f"Input file {args.input} does not exist.")

    # Validate task argument based on dim
    if args.dim in ['d', 'f'] and not args.task:
        parser.error("--task is required when --dim is 'd' or 'f'.")
    elif args.dim == 'n' and args.task:
        parser.error("--task is not allowed when --dim is 'n'.")

    # Generate default output file name if not provided
    if not args.output:
        if args.dim == 'n':
            args.task = 'only'
        input_base = os.path.dirname(args.input)
        output_base= f"{input_base.split('/')[0]}/{input_base.split('/')[1]}"
        args.output = f"{output_base}/output/{args.dim}/{args.task}/{args.test_model}_{args.dim}_{args.task}_metric.json"
        os.makedirs(os.path.dirname(args.output), exist_ok=True)

    process_metrics(args.dim, args.task, args.input, args.output)


if __name__ == "__main__":
    main()