from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import base64
import pymysql
from datetime import datetime

app = Flask(__name__)
CORS(app, resources=r'/*')	# 注册CORS, "/*" 允许访问所有api

dbcon = pymysql.connect(
  host="127.0.0.1",
  user="root",
  password="root",
  db="data",
  port=3306,
  charset='utf8mb4',
  connect_timeout=60,
)

# dbcon = pymysql.connect(
#   host="10.156.8.21",
#   user="root",
#   password="root",
#   db="data",
#   port=3306,
#   charset='utf8mb4',
#   connect_timeout=60,
# )

UPLOAD_FOLDER = 'uploaded_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 不同类型对应的文件夹名称
TYPE_FOLDERS = {
    'annotation': 'annotation',
    'segment': 'segment',
    'reconstruct': 'reconstruct',
}

SEGMENTATION_API_URL = 'http://10.156.8.34:5000/segment'

# 在需要使用数据库的地方调用该函数获取数据库连接
def get_db_connection():
    try:
        dbcon.ping(reconnect=True)
        return dbcon
    except pymysql.err.OperationalError as e:
        # 如果连接断开，则重新连接
        dbcon.connect()
        return dbcon

@app.route('/upload', methods=['POST'])
def upload():
    image = request.files['image']
    uuid = request.form['uuid']
    type = request.form['type']
    targetword = request.form['targetword']

    # 确定存储图片的位置
    if type in TYPE_FOLDERS:
        type_folder = TYPE_FOLDERS[type]
        segment_folder = os.path.join(app.config['UPLOAD_FOLDER'], type_folder, uuid)
        os.makedirs(segment_folder, exist_ok=True)

        input_folder = os.path.join(segment_folder, 'input')
        output_folder = os.path.join(segment_folder, 'output')
        os.makedirs(input_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

        # 保存输入图片到input文件夹下
        image_path = os.path.join(input_folder, image.filename)
        image.save(image_path)
    else:
        # 如果type不在配置中，直接保存到根文件夹下
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        image.save(image_path)

    # 调用分割算法接口
    files = {'imageFile': open(image_path, 'rb')}
    data = {'text_prompt': targetword}
    response = requests.post(SEGMENTATION_API_URL, files=files, data=data)
    if response is None:
        print("None")

    # 处理分割算法接口返回的结果
    if response.status_code == 200:
        segmentation_results = response.json()
        segmented_images = []

        # 保存分割后的图片到output文件夹并将 BASE64 数据提取出来
        for result in segmentation_results:
            filename = result['filename']
            data = result['data']
            segmented_images.append({
                'filename': filename,
                'base64_data': data
            })
            # 将 BASE64 数据解码并保存到output文件夹
            with open(os.path.join(output_folder, filename), 'wb') as f:
                f.write(base64.b64decode(data))

        # 将信息存入数据库
        storage_location = os.path.join(segment_folder, 'output')
        segmentation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = get_db_connection().cursor()
        sql = "INSERT INTO culture_data (type, uuid, time, photo_location) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (type, uuid, segmentation_time, storage_location))
        dbcon.commit()
        cursor.close()

        # 返回分割后的图片信息给前端
        return jsonify({
            'uuid': uuid,
            'segmented_images': segmented_images
        })
    else:
        return jsonify({'error': 'Failed to call segmentation API'}), 500


@app.route('/comment', methods=['POST'])
def comment():
    uuid = request.form['uuid']
    speedRating = request.form['speedRating']
    effectivenessRating = request.form['effectivenessRating']
    feedbackText = request.form['feedbackText']

    # 检查数据库中是否已经存在对应 UUID 的评价
    cursor = get_db_connection().cursor()
    cursor.execute("SELECT * FROM culture_data WHERE uuid = %s", (uuid,))
    existing_comment = cursor.fetchone()
    cursor.close()

    if existing_comment and all(existing_comment[1:]):
        # 如果已经存在评价且评价字段都不为空，则返回错误信息
        return jsonify({'code': 400, 'message': '不能重复评价'})

    # 打印要执行的 SQL 语句
    sql = "UPDATE culture_data SET speedRating=%s, effectivenessRating=%s, feedbackText=%s WHERE uuid = %s"
    print("Executing SQL statement:", sql % (speedRating, effectivenessRating, feedbackText, uuid))

    # 将信息存入数据库
    cursor = get_db_connection().cursor()
    cursor.execute(sql, (speedRating, effectivenessRating, feedbackText, uuid))
    dbcon.commit()
    cursor.close()

    # 返回一些信息
    return jsonify({'code': 200, 'message': '评论成功'})


@app.route('/get_colors', methods=['POST'])
def get_colors():
    # 获取上传的图片和数量参数
    image = request.files['image']
    count = request.form['count']

    # 调用另一个HTTP服务获取颜色信息
    url = "http://39.107.97.152:8096/color"
    files = {'image': image}
    data = {'count': count}
    response = requests.post(url, files=files, data=data)

    # 解析返回的JSON数据
    result = response.json()

    # 将结果原样返回给前端
    return jsonify(result)




if __name__ == '__main__':
    app.run(host="0.0.0.0",port=7777)
