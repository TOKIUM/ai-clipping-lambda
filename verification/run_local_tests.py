import csv
import subprocess
import os
import pathlib
import multiprocessing
import argparse

# CSVファイルへのパス
csv_file_path = 'data/clipping_0521.csv'
# local_test.pyへのパス
local_test_script_path = 'local_test.py'
# 出力ディレクトリ名
output_dir_name = 'output_jsons'
# デフォルトの並列プロセス数（Noneの場合はCPUコア数を使用）
default_num_processes = 4

def process_file(target_file_path_tuple):
    """
    単一のファイルを処理し、local_test.py を実行する関数。
    multiprocessing.Pool.map を使うため、引数はタプルで受け取る。
    """
    i, target_file_path = target_file_path_tuple # enumerateのインデックスも受け取る場合

    if not target_file_path:
        print(f"警告: ファイルパスが空です。スキップします。 (元CSV行: {i+2})") # iは0始まりなので+2
        return

    # 出力ファイル名を生成
    base_file_name = pathlib.Path(target_file_path).stem
    output_file_name = f"{base_file_name}_output.json"
    output_file_path = pathlib.Path(output_dir_name) / output_file_name

    # local_test.py を実行するコマンド
    command = [
        'python',
        local_test_script_path,
        f"data/{target_file_path}",
        '-o',
        str(output_file_path)
    ]

    print(f"実行中: {' '.join(command)}")
    try:
        # コマンドを実行
        process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        print(f"成功: {target_file_path} の結果を {output_file_path} に保存しました。")
        if process.stdout:
            # 大量の出力を避けるため、ここではstdout/stderrの詳細は表示しない
            # 必要であればファイルに書き出すなどの対応を検討
            pass
        if process.stderr:
            # print(f"STDERR for {target_file_path}:\n{process.stderr}")
            pass
    except subprocess.CalledProcessError as e:
        print(f"エラー: {target_file_path} の処理中にエラーが発生しました。")
        print(f"コマンド: {' '.join(e.cmd)}")
        print(f"リターンコード: {e.returncode}")
        # エラー出力が長い場合があるので注意
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
    except FileNotFoundError:
        print(f"エラー: pythonコマンドまたは {local_test_script_path} が見つかりません。パスを確認してください。")
    except Exception as e:
        print(f"予期せぬエラーが {target_file_path} の処理中に発生しました: {e}")
    print("-" * 30)


def main():
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='CSVファイルから並列でファイル処理を実行')
    parser.add_argument('-p', '--processes', type=int, default=default_num_processes, 
                       help=f'並列プロセス数 (デフォルト: {default_num_processes})')
    args = parser.parse_args()
    
    # 出力ディレクトリを作成 (存在しない場合)
    pathlib.Path(output_dir_name).mkdir(parents=True, exist_ok=True)

    tasks = []
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            csv_reader = csv.reader(csvfile)
            header = next(csv_reader)  # ヘッダー行をスキップ

            # "ファイルパス" 列のインデックスを取得
            try:
                file_path_column_index = header.index('ファイルパス')
            except ValueError:
                print(f"エラー: CSVファイルに 'ファイルパス' というヘッダーが見つかりません。")
                return # main関数を終了

            for i, row in enumerate(csv_reader):
                if len(row) > file_path_column_index:
                    target_file_path = row[file_path_column_index]
                    if target_file_path:
                        tasks.append((i, target_file_path)) # インデックスとファイルパスをタプルで追加
                    else:
                        print(f"警告: {i+2}行目のファイルパスが空です。スキップします。")
                else:
                    print(f"警告: {i+2}行目のデータが不足しています。スキップします。")

    except FileNotFoundError:
        print(f"エラー: CSVファイル {csv_file_path} が見つかりません。")
        return
    except Exception as e:
        print(f"CSV読み込み中に予期せぬエラーが発生しました: {e}")
        return

    if not tasks:
        print("処理対象のファイルが見つかりませんでした。")
        return

    # 並列プロセス数を取得（コマンドライン引数またはデフォルト値を使用）
    num_processes = args.processes
    if num_processes is None:
        num_processes = multiprocessing.cpu_count()
    
    print(f"{len(tasks)} 件のファイルを {num_processes} プロセスで並列処理します。")

    with multiprocessing.Pool(processes=num_processes) as pool:
        pool.map(process_file, tasks)

    print("全ての処理が完了しました。")

if __name__ == '__main__':
    main()