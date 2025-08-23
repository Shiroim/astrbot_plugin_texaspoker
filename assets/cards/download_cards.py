#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扑克牌素材下载和生成器

此脚本用于创建高质量的扑克牌素材图片，包括：
- 52张标准扑克牌的正面
- 统一的牌背设计
- 优化的尺寸和质量
"""

import os
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple

# 扑克牌配置
SUITS = ['spades', 'hearts', 'diamonds', 'clubs']  # 黑桃、红桃、方块、梅花  
SUIT_SYMBOLS = {'spades': '♠', 'hearts': '♥', 'diamonds': '♦', 'clubs': '♣'}
SUIT_COLORS = {'spades': 'black', 'hearts': 'red', 'diamonds': 'red', 'clubs': 'black'}
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

# 卡片尺寸 (扑克牌标准比例 5:7)
CARD_WIDTH = 200
CARD_HEIGHT = 280
CORNER_RADIUS = 20

# 颜色配置
BLACK_COLOR = (0, 0, 0, 255)
RED_COLOR = (220, 20, 20, 255) 
WHITE_COLOR = (255, 255, 255, 255)
BACKGROUND_COLOR = (255, 255, 255, 255)
BORDER_COLOR = (0, 0, 0, 255)

def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """获取字体"""
    try:
        if bold:
            return ImageFont.truetype("arial.ttf", size)
        else:
            return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

def draw_rounded_rectangle(draw: ImageDraw.Draw, xy: List[Tuple[int, int]], 
                          radius: int, fill=None, outline=None, width=1):
    """绘制圆角矩形"""
    x1, y1, x2, y2 = xy[0][0], xy[0][1], xy[1][0], xy[1][1]
    
    # 绘制主体矩形
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    
    # 绘制四个角的圆
    draw.ellipse([x1, y1, x1 + 2*radius, y1 + 2*radius], fill=fill)
    draw.ellipse([x2 - 2*radius, y1, x2, y1 + 2*radius], fill=fill)
    draw.ellipse([x1, y2 - 2*radius, x1 + 2*radius, y2], fill=fill)
    draw.ellipse([x2 - 2*radius, y2 - 2*radius, x2, y2], fill=fill)
    
    if outline:
        # 绘制边框
        draw.arc([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=outline, width=width)
        draw.arc([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=outline, width=width)
        draw.arc([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=outline, width=width)
        
        draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=width)
        draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=width)
        draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=width)
        draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=width)

def create_card_front(rank: str, suit: str) -> Image.Image:
    """创建扑克牌正面"""
    # 创建画布
    card = Image.new('RGBA', (CARD_WIDTH, CARD_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card)
    
    # 绘制卡片边框
    draw_rounded_rectangle(draw, [(2, 2), (CARD_WIDTH-3, CARD_HEIGHT-3)], 
                          CORNER_RADIUS, fill=WHITE_COLOR, outline=BORDER_COLOR, width=3)
    
    # 获取颜色和符号
    color = RED_COLOR if SUIT_COLORS[suit] == 'red' else BLACK_COLOR
    symbol = SUIT_SYMBOLS[suit]
    
    # 字体设置
    rank_font_large = get_font(40, bold=True)
    rank_font_small = get_font(24, bold=True)
    suit_font_large = get_font(80)
    suit_font_small = get_font(36)
    
    # 左上角的牌值和花色
    draw.text((15, 15), rank, font=rank_font_large, fill=color)
    draw.text((15, 60), symbol, font=suit_font_small, fill=color)
    
    # 右下角的牌值和花色（旋转180度的效果）
    # 计算文本尺寸
    rank_bbox = draw.textbbox((0, 0), rank, font=rank_font_large)
    rank_width = rank_bbox[2] - rank_bbox[0]
    rank_height = rank_bbox[3] - rank_bbox[1]
    
    symbol_bbox = draw.textbbox((0, 0), symbol, font=suit_font_small)
    symbol_width = symbol_bbox[2] - symbol_bbox[0]
    symbol_height = symbol_bbox[3] - symbol_bbox[1]
    
    # 右下角位置
    draw.text((CARD_WIDTH - rank_width - 15, CARD_HEIGHT - rank_height - 60), 
              rank, font=rank_font_large, fill=color)
    draw.text((CARD_WIDTH - symbol_width - 15, CARD_HEIGHT - symbol_height - 15), 
              symbol, font=suit_font_small, fill=color)
    
    # 中央大花色符号
    center_symbol_bbox = draw.textbbox((0, 0), symbol, font=suit_font_large)
    center_symbol_width = center_symbol_bbox[2] - center_symbol_bbox[0]
    center_symbol_height = center_symbol_bbox[3] - center_symbol_bbox[1]
    
    center_x = (CARD_WIDTH - center_symbol_width) // 2
    center_y = (CARD_HEIGHT - center_symbol_height) // 2
    draw.text((center_x, center_y), symbol, font=suit_font_large, fill=color)
    
    return card

def create_card_back() -> Image.Image:
    """创建扑克牌背面"""
    # 创建画布
    card = Image.new('RGBA', (CARD_WIDTH, CARD_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card)
    
    # 绘制卡片边框
    draw_rounded_rectangle(draw, [(2, 2), (CARD_WIDTH-3, CARD_HEIGHT-3)], 
                          CORNER_RADIUS, fill=WHITE_COLOR, outline=BORDER_COLOR, width=3)
    
    # 背景颜色
    bg_color = (25, 50, 125, 255)  # 深蓝色
    draw_rounded_rectangle(draw, [(8, 8), (CARD_WIDTH-9, CARD_HEIGHT-9)], 
                          CORNER_RADIUS-4, fill=bg_color)
    
    # 绘制装饰图案
    pattern_color = (255, 255, 255, 180)
    
    # 绘制菱形网格图案
    diamond_size = 15
    spacing = 25
    
    for x in range(30, CARD_WIDTH - 30, spacing):
        for y in range(30, CARD_HEIGHT - 30, spacing):
            # 绘制小菱形
            diamond_points = [
                (x, y + diamond_size//2),
                (x + diamond_size//2, y),
                (x + diamond_size, y + diamond_size//2),
                (x + diamond_size//2, y + diamond_size)
            ]
            draw.polygon(diamond_points, fill=pattern_color)
    
    # 中央标志
    center_x, center_y = CARD_WIDTH // 2, CARD_HEIGHT // 2
    font = get_font(24, bold=True)
    text = "AstrBot"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # 绘制文本背景
    bg_x1 = center_x - text_width//2 - 10
    bg_y1 = center_y - text_height//2 - 5
    bg_x2 = center_x + text_width//2 + 10
    bg_y2 = center_y + text_height//2 + 5
    
    draw_rounded_rectangle(draw, [(bg_x1, bg_y1), (bg_x2, bg_y2)], 
                          8, fill=(255, 255, 255, 200))
    
    # 绘制文本
    draw.text((center_x - text_width//2, center_y - text_height//2), 
              text, font=font, fill=(25, 50, 125, 255))
    
    return card

def generate_all_cards():
    """生成所有扑克牌"""
    # 确保目录存在
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    
    print("生成扑克牌素材...")
    
    # 生成牌背
    print("生成牌背...")
    back_card = create_card_back()
    back_path = os.path.join(os.path.dirname(__file__), "back.png")
    back_card.save(back_path, 'PNG', optimize=True)
    print(f"牌背已保存: {back_path}")
    
    # 生成52张牌
    card_count = 0
    for suit in SUITS:
        for rank in RANKS:
            print(f"生成 {rank} of {suit}...")
            card = create_card_front(rank, suit)
            filename = f"{rank.lower()}_{suit}.png"
            filepath = os.path.join(os.path.dirname(__file__), filename)
            card.save(filepath, 'PNG', optimize=True)
            card_count += 1
    
    print(f"完成！共生成 {card_count + 1} 张扑克牌图片（包括牌背）")

if __name__ == "__main__":
    generate_all_cards()
