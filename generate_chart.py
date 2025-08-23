import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties

# 指定中文字體路徑
font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
# 載入字體
chinese_font = FontProperties(fname=font_path)

# 準備數據
x = np.linspace(0, 10, 100)
y = np.sin(x)

# 創建圖表
plt.figure(figsize=(8, 6))
plt.plot(x, y, label='sin(x)')

# 添加標題和標籤 (使用繁體中文和指定的字體)
plt.title("正弦函數圖表", fontproperties=chinese_font)
plt.xlabel("X 軸", fontproperties=chinese_font)
plt.ylabel("Y 軸", fontproperties=chinese_font)


# 添加圖例
plt.legend()

# 添加網格
plt.grid(True)

# 清除舊的 matplotlib 字體快取
# import matplotlib
# matplotlib.font_manager._rebuild()

# 保存圖表為圖片文件
plt.savefig("chart.png")

print("圖表已成功生成並保存為 chart.png")
