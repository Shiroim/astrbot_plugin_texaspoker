"""德州扑克图形渲染系统

提供完整的德州扑克游戏图形渲染功能：
- 扑克牌渲染（支持正面和背面）
- 玩家手牌图形生成
- 公共牌区域渲染
- 游戏结算界面生成
- 临时文件管理和清理
"""
import os
import tempfile
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from ..models.card import Card, Suit, Rank
from ..models.game import TexasHoldemGame, Player
from .hand_evaluator import HandEvaluator, HandRank
from astrbot.api import logger


class PokerRenderer:
    """
    德州扑克图形渲染器
    
    提供高质量的扑克牌和游戏界面渲染功能，支持：
    - 精美的扑克牌图形
    - 自适应的界面布局
    - 字体缓存优化
    - 临时文件管理
    """
    
    def __init__(self):
        self.assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
        self.card_width = 120
        self.card_height = 168
        self.font_cache = {}
        
        # 临时文件管理
        self.temp_dir = None
        self._init_temp_dir()
    
    def _init_temp_dir(self) -> None:
        """初始化临时文件目录"""
        try:
            # 使用系统临时目录的子目录
            base_temp = tempfile.gettempdir()
            self.temp_dir = os.path.join(base_temp, "astrbot_texaspoker")
            
            # 确保目录存在
            os.makedirs(self.temp_dir, exist_ok=True)
            
            logger.debug(f"渲染器临时目录: {self.temp_dir}")
            
        except Exception as e:
            logger.warning(f"初始化临时目录失败: {e}")
            self.temp_dir = tempfile.gettempdir()
    
    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """获取字体（带缓存）"""
        font_key = f"{size}_{bold}"
        if font_key not in self.font_cache:
            try:
                font_path = os.path.join(self.assets_dir, "fonts", "arial.ttf")
                if not os.path.exists(font_path):
                    # 使用系统默认字体
                    self.font_cache[font_key] = ImageFont.load_default()
                else:
                    self.font_cache[font_key] = ImageFont.truetype(font_path, size)
            except Exception:
                self.font_cache[font_key] = ImageFont.load_default()
        return self.font_cache[font_key]
    
    def _create_card_image(self, card: Card, face_up: bool = True) -> Image.Image:
        """创建单张扑克牌图像"""
        # 创建卡片背景
        card_img = Image.new('RGBA', (self.card_width, self.card_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(card_img)
        
        # 绘制卡片边框
        border_color = (0, 0, 0, 255)
        corner_radius = 12
        
        # 绘制圆角矩形
        self._draw_rounded_rectangle(draw, [(0, 0), (self.card_width-1, self.card_height-1)], 
                                   corner_radius, fill=(255, 255, 255, 255), outline=border_color, width=2)
        
        if not face_up:
            # 绘制牌背
            self._draw_card_back(draw)
        else:
            # 绘制牌面
            self._draw_card_face(draw, card)
        
        return card_img
    
    def _draw_rounded_rectangle(self, draw: ImageDraw.Draw, bbox: List[Tuple[int, int]], 
                              radius: int, fill=None, outline=None, width=1):
        """绘制圆角矩形"""
        x1, y1 = bbox[0]
        x2, y2 = bbox[1]
        
        # 绘制主体矩形
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        
        # 绘制四个角的圆形
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
    
    def _draw_card_back(self, draw: ImageDraw.Draw):
        """绘制牌背图案"""
        # 简单的几何图案
        center_x, center_y = self.card_width // 2, self.card_height // 2
        
        # 绘制菱形图案
        pattern_color = (0, 50, 100, 255)
        for i in range(3):
            for j in range(4):
                x = 20 + i * 30
                y = 20 + j * 35
                diamond_points = [
                    (x, y + 10), (x + 10, y), (x + 20, y + 10), (x + 10, y + 20)
                ]
                draw.polygon(diamond_points, fill=pattern_color)
    
    def _draw_card_face(self, draw: ImageDraw.Draw, card: Card):
        """绘制牌面"""
        # 确定颜色
        color = (220, 0, 0, 255) if card.is_red else (0, 0, 0, 255)
        
        # 获取牌面和花色字符
        rank_str = self._get_rank_string(card.rank)
        suit_str = card.suit.value
        
        # 绘制左上角的牌值和花色
        font_large = self._get_font(28, bold=True)
        font_small = self._get_font(20)
        
        # 左上角
        draw.text((8, 5), rank_str, font=font_large, fill=color)
        draw.text((8, 35), suit_str, font=font_small, fill=color)
        
        # 右下角（旋转180度的效果）
        text_bbox = draw.textbbox((0, 0), rank_str, font=font_large)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        draw.text((self.card_width - text_width - 8, self.card_height - text_height - 35), 
                 rank_str, font=font_large, fill=color)
        draw.text((self.card_width - 20 - 8, self.card_height - 25 - 5), 
                 suit_str, font=font_small, fill=color)
        
        # 中央绘制大花色符号
        font_huge = self._get_font(60)
        suit_bbox = draw.textbbox((0, 0), suit_str, font=font_huge)
        suit_width = suit_bbox[2] - suit_bbox[0]
        suit_height = suit_bbox[3] - suit_bbox[1]
        
        center_x = (self.card_width - suit_width) // 2
        center_y = (self.card_height - suit_height) // 2
        draw.text((center_x, center_y), suit_str, font=font_huge, fill=color)
    
    def _get_rank_string(self, rank: Rank) -> str:
        """获取牌值字符串"""
        rank_map = {
            Rank.ACE: "A", Rank.KING: "K", Rank.QUEEN: "Q", Rank.JACK: "J",
            Rank.TEN: "10", Rank.NINE: "9", Rank.EIGHT: "8", Rank.SEVEN: "7",
            Rank.SIX: "6", Rank.FIVE: "5", Rank.FOUR: "4", Rank.THREE: "3", 
            Rank.TWO: "2"
        }
        return rank_map[rank]
    
    def render_hand_cards(self, player: Player, game: TexasHoldemGame) -> Image.Image:
        """渲染玩家手牌图片"""
        # 创建画布
        canvas_width = 600
        canvas_height = 400
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (34, 139, 34, 255))  # 深绿色背景
        
        # 绘制标题区域
        self._draw_title_area(canvas, f"{player.nickname} 的手牌", game.game_id)
        
        # 绘制手牌
        if len(player.hole_cards) >= 2:
            card1_img = self._create_card_image(player.hole_cards[0])
            card2_img = self._create_card_image(player.hole_cards[1])
            
            # 计算卡片位置
            total_width = 2 * self.card_width + 20  # 两张牌加间距
            start_x = (canvas_width - total_width) // 2
            start_y = 120
            
            canvas.paste(card1_img, (start_x, start_y), card1_img)
            canvas.paste(card2_img, (start_x + self.card_width + 20, start_y), card2_img)
        
        # 绘制玩家信息
        self._draw_player_info(canvas, player, 50, 300)
        
        return canvas
    
    def render_community_cards(self, game: TexasHoldemGame) -> Image.Image:
        """渲染公共牌区域"""
        # 创建画布
        canvas_width = 800
        canvas_height = 400
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (34, 139, 34, 255))
        
        # 绘制标题
        title = f"游戏 {game.game_id} - {game.phase.value.upper()}"
        self._draw_title_area(canvas, title, f"底池: {game.pot}")
        
        # 绘制5张公共牌位置
        card_spacing = 20
        total_width = 5 * self.card_width + 4 * card_spacing
        start_x = (canvas_width - total_width) // 2
        start_y = 120
        
        for i in range(5):
            x = start_x + i * (self.card_width + card_spacing)
            
            if i < len(game.community_cards):
                # 已翻开的牌
                card_img = self._create_card_image(game.community_cards[i])
            else:
                # 未翻开的牌（牌背）
                card_img = self._create_card_image(Card(Suit.SPADES, Rank.ACE), face_up=False)
            
            canvas.paste(card_img, (x, start_y), card_img)
        
        return canvas
    
    def render_showdown(self, game: TexasHoldemGame, winners: List[Player]) -> Image.Image:
        """渲染摊牌结果"""
        # 创建更大的画布
        canvas_width = 1000
        canvas_height = 600
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (34, 139, 34, 255))
        
        # 绘制标题
        self._draw_title_area(canvas, f"游戏 {game.game_id} 结算", f"底池: {game.pot}")
        
        # 绘制公共牌
        self._draw_community_cards_compact(canvas, game.community_cards, 50, 80)
        
        # 绘制所有未弃牌玩家的手牌
        active_players = [p for p in game.players if not p.is_folded]
        y_offset = 200
        
        for i, player in enumerate(active_players):
            is_winner = player in winners
            self._draw_player_showdown(canvas, player, game.community_cards, 50, y_offset, is_winner)
            y_offset += 120
        
        return canvas
    
    def _draw_title_area(self, canvas: Image.Image, title: str, subtitle: str):
        """绘制标题区域"""
        draw = ImageDraw.Draw(canvas)
        
        # 标题背景
        draw.rectangle([0, 0, canvas.width, 60], fill=(0, 0, 0, 180))
        
        # 标题文字
        title_font = self._get_font(24, bold=True)
        subtitle_font = self._get_font(16)
        
        draw.text((20, 10), title, font=title_font, fill=(255, 255, 255, 255))
        draw.text((20, 35), subtitle, font=subtitle_font, fill=(200, 200, 200, 255))
    
    def _draw_player_info(self, canvas: Image.Image, player: Player, x: int, y: int):
        """绘制玩家信息"""
        draw = ImageDraw.Draw(canvas)
        font = self._get_font(18)
        
        info_lines = [
            f"玩家: {player.nickname}",
            f"筹码: {player.chips}",
            f"当前下注: {player.current_bet}",
        ]
        
        for i, line in enumerate(info_lines):
            draw.text((x, y + i * 25), line, font=font, fill=(255, 255, 255, 255))
    
    def _draw_community_cards_compact(self, canvas: Image.Image, community_cards: List[Card], x: int, y: int):
        """绘制紧凑版公共牌"""
        card_width_small = 60
        card_height_small = 84
        spacing = 10
        
        for i, card in enumerate(community_cards):
            card_img = self._create_card_image(card)
            card_img = card_img.resize((card_width_small, card_height_small), Image.Resampling.LANCZOS)
            
            card_x = x + i * (card_width_small + spacing)
            canvas.paste(card_img, (card_x, y), card_img)
    
    def _draw_player_showdown(self, canvas: Image.Image, player: Player, community_cards: List[Card], 
                            x: int, y: int, is_winner: bool):
        """绘制玩家摊牌信息"""
        draw = ImageDraw.Draw(canvas)
        
        # 背景色
        bg_color = (255, 215, 0, 100) if is_winner else (0, 0, 0, 50)
        draw.rectangle([x, y, canvas.width - 20, y + 100], fill=bg_color)
        
        # 玩家信息
        font = self._get_font(16, bold=is_winner)
        status = "🏆 获胜者" if is_winner else ""
        draw.text((x + 10, y + 10), f"{player.nickname} {status}", font=font, 
                 fill=(255, 255, 255, 255))
        
        # 绘制手牌（小尺寸）
        card_size = 40
        for i, card in enumerate(player.hole_cards):
            card_img = self._create_card_image(card)
            card_img = card_img.resize((card_size, card_size * 168 // 120), Image.Resampling.LANCZOS)
            canvas.paste(card_img, (x + 200 + i * (card_size + 5), y + 10), card_img)
        
        # 评估并显示牌型
        if community_cards:
            hand_rank, values = HandEvaluator.evaluate_hand(player.hole_cards, community_cards)
            hand_desc = HandEvaluator.get_hand_description(hand_rank, values)
            draw.text((x + 200, y + 60), f"牌型: {hand_desc}", font=self._get_font(14), 
                     fill=(255, 255, 255, 255))
        
        # 筹码信息
        draw.text((x + 10, y + 35), f"筹码: {player.chips}", font=self._get_font(14), 
                 fill=(255, 255, 255, 255))
    
    def save_image(self, image: Image.Image, filename: str) -> Optional[str]:
        """
        保存图像到临时文件
        
        Args:
            image: PIL图像对象
            filename: 文件名
            
        Returns:
            保存的文件路径，失败返回None
        """
        try:
            if not self.temp_dir:
                logger.error("临时目录未初始化")
                return None
            
            # 确保文件名安全
            safe_filename = self._sanitize_filename(filename)
            filepath = os.path.join(self.temp_dir, safe_filename)
            
            # 保存图像
            image.save(filepath, 'PNG', quality=95, optimize=True)
            
            logger.debug(f"图像已保存: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"保存图像失败: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，确保安全
        
        Args:
            filename: 原始文件名
            
        Returns:
            安全的文件名
        """
        import re
        # 移除危险字符
        safe_name = re.sub(r'[^\w\-_\.]', '_', filename)
        # 确保.png扩展名
        if not safe_name.lower().endswith('.png'):
            safe_name += '.png'
        return safe_name
    
    def cleanup_temp_files(self, pattern: Optional[str] = None) -> int:
        """
        清理临时文件
        
        Args:
            pattern: 文件名模式（可选），如None则清理所有文件
            
        Returns:
            清理的文件数量
        """
        cleaned_count = 0
        
        try:
            if not self.temp_dir or not os.path.exists(self.temp_dir):
                return 0
            
            import glob
            
            if pattern:
                # 清理匹配模式的文件
                search_pattern = os.path.join(self.temp_dir, pattern)
                files_to_clean = glob.glob(search_pattern)
            else:
                # 清理所有PNG文件
                files_to_clean = glob.glob(os.path.join(self.temp_dir, "*.png"))
            
            for filepath in files_to_clean:
                try:
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                        cleaned_count += 1
                        logger.debug(f"已删除临时文件: {filepath}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {filepath}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"已清理 {cleaned_count} 个临时文件")
            
        except Exception as e:
            logger.error(f"清理临时文件时出错: {e}")
        
        return cleaned_count
    
    def cleanup_game_files(self, game_id: str) -> int:
        """
        清理指定游戏的所有临时文件
        
        Args:
            game_id: 游戏ID
            
        Returns:
            清理的文件数量
        """
        return self.cleanup_temp_files(f"*{game_id}*.png")
    
    def get_temp_file_count(self) -> int:
        """
        获取临时文件数量
        
        Returns:
            临时文件数量
        """
        try:
            if not self.temp_dir or not os.path.exists(self.temp_dir):
                return 0
            
            import glob
            files = glob.glob(os.path.join(self.temp_dir, "*.png"))
            return len(files)
            
        except Exception as e:
            logger.warning(f"统计临时文件时出错: {e}")
            return 0
