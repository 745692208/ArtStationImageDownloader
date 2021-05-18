import os
import re
from concurrent import futures
from multiprocessing import cpu_count

import requests   # pip install --upgrade urllib3==1.25.2
from pytube import YouTube  # https://pytube.io/en/latest/user/install.html


b_is_create_folder = True
b_is_custom_name = True
entry_path = ''
save_path = ''
futures_list = []


class Core:
    def log(self, message):
        print(message)

    def __init__(self, log_print=None):
        if log_print:  # 好像是靠这个捕获打印。然后调用app.py里的函数。
            global print
            print = log_print
        max_workers = cpu_count() * 4
        self.session = requests.session()
        # 异步加载，避免GUI卡顿
        self.executor = futures.ThreadPoolExecutor(max_workers)
        self.executor_video = futures.ThreadPoolExecutor(1)
        self.futures_list = []
        self.b_is_create_folder = True
        self.b_is_down_video = True
        self.b_is_custom_name = True
        self.entry_path = ''    # 文件保存路径
        self.save_path = ''     # 保存路径

    def get_user_works(self, url):  # 获取用户的所有作品
        '''
        :param url, str, 网页地址，比如：https://www.artstation.com/pouria_roshan
        '''
        self.log('分析中，请不要进行操作...')
        username = url.split('/')[-1]
        data = []
        page = 0    # 一页最大data数为50，0~49，page为1起步
        while True:
            page += 1
            url = 'https://www.artstation.com/users/{}/projects.json?page={}'\
                .format(username, page)
            try:
                j = self.session.get(url).json()
            except Exception:
                self.log('[错误]下载失败，请检查网络、网页问题；')
                return
            total_count = int(j['total_count'])
            data += j['data']
            if page > total_count / 50:
                break
        self.log('分析完毕，作者：{}，共计{}个作品，现进行作品分析... '.format(username, len(data)))
        futures_list = []
        for wrok in data:
            futures_list.append(
                self.executor.submit(
                    self.get_work, wrok['permalink']))
        futures.wait(futures_list)
        self.log("[正常]爬取用户作品的下载任务已全部完成；\n")

    def get_work(self, url):
        '''
        获取单独作品
        :param url, str, 网页地址，比如：https://www.artstation.com/artwork/5X9mYA
        '''
        self.log('分析网址：{}中，请不要进行操作...'.format(url))
        # 1 获取json数据网址
        url = 'https://www.artstation.com/projects/{}.json'.format(
            url.rsplit('/', 1)[1])
        # 2 获取json资产数据
        try:
            r = self.session.get(url)
            if r.status_code == 403:
                err = "[Error] [{} {}] ".format(r.status_code, r.reason)
                self.log(err + "You are blocked by artstation")
            j = r.json()
        except Exception:
            self.log('[错误]下载失败，请检查网络设置；')
            return
        assets = j['assets']    # 获取资产
        for i, asset in enumerate(assets):    # 删除多余资产
            if asset['asset_type'] == 'cover':
                del assets[i]
        # 创建文件夹
        self.save_path = self.entry_path
        if self.b_is_create_folder:
            title = j['title'].strip()   # 获取标题
            title = re.sub(r'[/\:*?"<>|]', "", title)    # 去除标题特殊符号
            self.save_path = os.path.join(self.entry_path, title)
            if not os.path.exists(self.save_path):   # 创建目录
                os.makedirs(self.save_path, exist_ok=True)
        # 3 资产数据分析
        self.log('分析完毕，作品：{}，现进行下载...'.format(j['title'].strip()))
        futures_list = []
        for i, asset in enumerate(assets):
            # time.sleep(0.1)
            if asset['asset_type'] == 'image':
                url = asset['image_url']
                file_name = self.get_file_name(asset['image_url'], i, 1)
                file_name = self.custom_name(j, file_name, i + 1)
                futures_list.append(
                    self.executor.submit(
                        self.down_file, url, file_name, self.save_path))
            if asset['asset_type'] == 'video' and self.b_is_down_video:
                url = re.findall(r'src="(.*?)"', asset['player_embedded'])[0]
                file_name = self.custom_name(j, 'name.mp4', i + 1)
                self.log('这是个视频，下载比较忙，亲耐心等候。')
                futures_list.append(
                    self.executor.submit(
                        self.down_youtube_video,
                        url, file_name, self.save_path))
            if asset['asset_type'] == 'video_clip' and self.b_is_down_video:
                url = re.findall(r"src='(.*?)'", asset['player_embedded'])[0]
                r = self.session.get(url)
                # 获取可下载的网页地址
                source_media = re.findall(r'src="(.*?)" type=', r.text)[0]
                file_name = self.get_file_name(source_media, i, 0)
                file_name = self.custom_name(j, file_name, i + 1)
                self.log('这是个视频，下载比较忙，亲耐心等候。')
                futures_list.append(
                    self.executor.submit(
                        self.down_file,
                        source_media, file_name, self.save_path))
        futures.wait(futures_list)
        self.log("[正常]下载任务已完成；\n")

    def zb_get_work(self, url):
        self.log("ZB下载任务开始中，亲稍等\n")
        r = self.session.get(url).text
        urls = re.findall(r'class="lightbox" href="//(.*?)"', r)
        futures_list = []
        for i, down_url in enumerate(urls):
            nameS = url.rsplit('/', 2)
            name = '{}-{}-{}.jpeg'.format(nameS[1], nameS[2], i + 1)
            down_url = 'https://' + down_url
            self.log("--name：{}--url：{}".format(name, url))
            futures_list.append(
                self.executor.submit(self.down_file, down_url, name, self.entry_path))
        futures.wait(futures_list)
        self.log("[正常]下载任务已完成；\n")

    def get_file_name(self, url, index, has_mask):
        '''把输入的网页地址转换成名字。
        :param url, str, 输入网页地址，
        如：https://cdna.artstation.com/..../gabriel-dias-maia-principal.jpg?1620144337；
        :param index, int, 尾缀index号；
        :param has_mask, bool, 网页地址的最后是否有问号，如上面的那个地址所示，去掉问号及其后面的东西；'''
        file_name = url.split('/')[-1]
        if has_mask:
            file_name = file_name.rsplit('?')[0]
        file_name = file_name.rsplit('.', 1)    # 分割名字和格式 name&jpg
        file_name = '{}-{}.{}'.format(file_name[0], index, file_name[1])
        return file_name

    def down_file(self, url, file_name, save_path):   # 下载图片
        '''
        :param url, str, 输入网页地址，如 https://cdna.artstation.com/p/1.jpg
        :param file_name, str, 文件保存名字，比如：asd.jpg
        :param save_path. str, 保存地址，比如：E:\asd
        '''
        r = self.session.get(url)  # 下载图片
        path = os.path.join(save_path, file_name)   # 保存路径和文件名字合并
        print(path)
        with open(path, 'wb') as f:
            f.write(r.content)
        self.log('完成下载，地址：{}'.format(url))

    def down_youtube_video(self, url, file_name, save_path):   # 下载视频
        '''
        :param url, str, 输入网页地址，如https://www.youtube.com/watch?v=3uVvUD-5Vl4；
        '''
        YouTube(url).streams.first().download(save_path, file_name)
        self.log('完成下载，地址：{}'.format(url))

    def custom_name(self, j, file_name, index):
        if self.b_is_custom_name:
            username = j['user']['username']
            work_id = j['hash_id']
            file_name = file_name.rsplit('.', 1)
            return '{}-{}-{}.{}'.format(username, work_id, index, file_name[1])
        else:
            return file_name


class ArtStation:
    def __init__(self) -> None:
        pass

    def get_user_works(self, url):  # 获取用户的所有作品
        '''
        :param url, str, 网页地址，比如：https://www.artstation.com/pouria_roshan
        '''
        self.log('分析中，请不要进行操作...')
        username = url.split('/')[-1]
        data = []
        page = 0    # 一页最大data数为50，0~49，page为1起步
        while True:
            page += 1
            url = 'https://www.artstation.com/users/{}/projects.json?page={}'\
                .format(username, page)
            try:
                j = self.session.get(url).json()
            except Exception:
                self.log('[错误]下载失败，请检查网络、网页问题；')
                return
            total_count = int(j['total_count'])
            data += j['data']
            if page > total_count / 50:
                break
        self.log('分析完毕，作者：{}，共计{}个作品，现进行作品分析... '.format(username, len(data)))
        futures_list = []
        for wrok in data:
            futures_list.append(
                self.executor.submit(
                    self.get_work, wrok['permalink']))
        futures.wait(futures_list)
        self.log("[正常]爬取用户作品的下载任务已全部完成；\n")

    def get_work(self, url):
        '''
        获取单独作品
        :param url, str, 网页地址，比如：https://www.artstation.com/artwork/5X9mYA
        '''
        self.log('分析网址：{}中，请不要进行操作...'.format(url))
        # 1 获取json数据网址
        url = 'https://www.artstation.com/projects/{}.json'.format(
            url.rsplit('/', 1)[1])
        # 2 获取json资产数据
        try:
            r = self.session.get(url)
            if r.status_code == 403:
                err = "[Error] [{} {}] ".format(r.status_code, r.reason)
                self.log(err + "You are blocked by artstation")
            j = r.json()
        except Exception:
            self.log('[错误]下载失败，请检查网络设置；')
            return
        assets = j['assets']    # 获取资产
        for i, asset in enumerate(assets):    # 删除多余资产
            if asset['asset_type'] == 'cover':
                del assets[i]
        # 创建文件夹
        self.save_path = self.entry_path
        if self.b_is_create_folder:
            title = j['title'].strip()   # 获取标题
            title = re.sub(r'[/\:*?"<>|]', "", title)    # 去除标题特殊符号
            self.save_path = os.path.join(self.entry_path, title)
            if not os.path.exists(self.save_path):   # 创建目录
                os.makedirs(self.save_path, exist_ok=True)
        # 3 资产数据分析
        self.log('分析完毕，作品：{}，现进行下载...'.format(j['title'].strip()))
        futures_list = []
        for i, asset in enumerate(assets):
            # time.sleep(0.1)
            if asset['asset_type'] == 'image':
                url = asset['image_url']
                file_name = self.get_file_name(asset['image_url'], i, 1)
                file_name = self.custom_name(j, file_name, i + 1)
                futures_list.append(
                    self.executor.submit(
                        self.down_file, url, file_name, self.save_path))
            if asset['asset_type'] == 'video' and self.b_is_down_video:
                url = re.findall(r'src="(.*?)"', asset['player_embedded'])[0]
                file_name = self.custom_name(j, 'name.mp4', i + 1)
                self.log('这是个视频，下载比较忙，亲耐心等候。')
                futures_list.append(
                    self.executor.submit(
                        self.down_youtube_video,
                        url, file_name, self.save_path))
            if asset['asset_type'] == 'video_clip' and self.b_is_down_video:
                url = re.findall(r"src='(.*?)'", asset['player_embedded'])[0]
                r = self.session.get(url)
                # 获取可下载的网页地址
                source_media = re.findall(r'src="(.*?)" type=', r.text)[0]
                file_name = self.get_file_name(source_media, i, 0)
                file_name = self.custom_name(j, file_name, i + 1)
                self.log('这是个视频，下载比较忙，亲耐心等候。')
                futures_list.append(
                    self.executor.submit(
                        self.down_file,
                        source_media, file_name, self.save_path))
        futures.wait(futures_list)
        self.log("[正常]下载任务已完成；\n")


class ZBrush:
    def __init__(self) -> None:
        pass

    def get_work(self, url):
        self.log("ZB下载任务开始中，亲稍等\n")
        r = self.session.get(url).text
        urls = re.findall(r'class="lightbox" href="//(.*?)"', r)
        futures_list = []
        for i, down_url in enumerate(urls):
            nameS = url.rsplit('/', 2)
            name = '{}-{}-{}.jpeg'.format(nameS[1], nameS[2], i + 1)
            down_url = 'https://' + down_url
            self.log("--name：{}--url：{}".format(name, url))
            futures_list.append(
                self.executor.submit(self.down_file, down_url, name, self.entry_path))
        futures.wait(futures_list)
        self.log("[正常]下载任务已完成；\n")


class utils:
    def __init__(self) -> None:
        pass

    def down_file(self, url, file_name, save_path):   # 下载图片
        '''下载输入的网址文件，并对其命名，保存到指定位置。
        :param url, str, 输入网页地址，如：https://cdna.artstation.com/p/1.jpg ;
        :param file_name, str, 文件保存名字，比如：awaw-5X9mYA-1.jpg ;
        :param save_path. str, 保存地址，比如：E:\asd '''
        r = self.session.get(url)  # 下载图片
        path = os.path.join(save_path, file_name)   # 保存路径和文件名字合并
        with open(path, 'wb') as f:
            f.write(r.content)
        self.log('完成下载，地址：{}'.format(url))

    def down_youtube_video(self, url, file_name, save_path):   # 下载视频
        '''下载输入的youtube网址，分析并下载，最后改名保存到指定路径。
        :param url, str, 输入网页地址，如https://www.youtube.com/watch?v=3uVvUD-5Vl4 ;'''
        YouTube(url).streams.first().download(save_path, file_name)
        self.log('完成下载，地址：{}'.format(url))

    def make_dir(slef):
        '''新建目录文件夹'''
        print('make_dir')

    def make_name(slef, name1, name2, index, format):
        '''通过输入的参数，合成名字，name1-name2-index.format'''
        print('make_name')
        return '{}-{}-{}.{}'.format(name1, name2, index, format)

    def make_save_path(slef):
        '''制作保存路径'''
        print('make_dir')


if __name__ == '__main__':
    pass
