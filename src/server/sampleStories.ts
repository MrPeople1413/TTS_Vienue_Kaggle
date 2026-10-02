export interface Chapter {
  id: string;
  title: string;
  author?: string;
  source?: string;
  content: string;
}

export const SAMPLE_STORIES: Chapter[] = [
  {
    id: 'tam-cam',
    title: 'Truyện Cổ Tích: Tấm Cám (Trích đoạn Bống Bống Bang Bang)',
    author: 'Văn học dân gian Việt Nam',
    source: 'Kho tàng truyện cổ tích Việt Nam',
    content: `Ngày xưa, có hai chị em cùng cha khác mẹ: chị tên là Tấm, em tên là Cám. Mẹ Tấm mất sớm, ít năm sau người cha cũng qua đời. Tấm ở với dì ghẻ là mẹ của Cám.

Dì ghẻ là người cay nghiệt, hằng ngày bắt Tấm phải làm lụng vất vả, từ việc quét nhà, gánh nước, cắt cỏ cho trâu đến nấu cơm, giặt giũ. Còn Cám thì được mẹ nuông chiều, chỉ quanh quẩn ăn trắng mặc trơn, không phải mó tay vào bất cứ việc gì.

Một hôm, người mẹ kế đưa cho hai chị em mỗi người một cái giỏ bảo ra đồng bắt tôm bắt tép. Bà hứa hẹn: "Hễ đứa nào bắt được đầy giỏ tép thì mẹ sẽ thưởng cho một chiếc yếm đào."

Ra đến đồng, Tấm chăm chỉ mò cua bắt ốc, ngụp lặn hết bờ này sang bụi khác, đến trưa thì chiếc giỏ đã đầy ắp tôm tép tươi rói. Trong khi đó, Cám mải mê hái hoa, đuổi bướm trên bờ ruộng, mãi đến chiều giỏ vẫn rỗng không.

Thấy giỏ của Tấm đầy ắp, Cám nghĩ kế lừa chị: "Chị Tấm ơi chị Tấm! Đầu chị lấm, chị hụp cho sâu, kẻo về mẹ mắng."

Tấm thật thà tin lời em, liền lội xuống ao sâu tắm rửa sạch sẽ. Trên bờ, Cám nhanh tay trút toàn bộ giỏ tép của Tấm sang giỏ mình rồi chạy một mạch về nhà nhận yếm đỏ.

Đến khi Tấm bước lên bờ, nhìn vào giỏ trống không, tủi thân liền ngồi bưng mặt khóc nức nở. Bỗng nhiên, một làn khói trắng tỏa ra mờ ảo, Bụt hiện lên với gương mặt hiền từ, râu tóc bạc phơ: "Làm sao con khóc?"

Tấm nghẹn ngào kể lại đầu đuôi câu chuyện. Bụt khẽ mỉm cười bảo: "Con hãy nhìn vào trong giỏ xem còn sót lại thứ gì không?"

Tấm nhìn vào giỏ thì thấy chỉ còn lại một con cá bống nhỏ bằng ngón tay út. Bụt dặn dò: "Con hãy đem con cá bống này về thả xuống giếng nuôi. Mỗi bữa ăn, con hãy bớt lại một bát cơm rồi ra giếng gọi: Bống bống bang bang, lên ăn cơm vàng cơm bạc nhà ta, chớ ăn cơm hẩm cháo hoa nhà người. Cá bống sẽ nổi lên đón lấy hạt cơm con cho."`,
  },
  {
    id: 'su-tich-cay-vu-sua',
    title: 'Truyện Dân Gian: Sự Tích Cây Vú Sữa',
    author: 'Truyện dân gian Việt Nam',
    source: 'Truyện đọc thiếu nhi',
    content: `Ngày xưa, có một cậu bé rất hiếu động và nghịch ngợm. Vì là con một nên cậu được mẹ hết lòng nuông chiều, chăm bẵm từng li từng tí.

Một hôm, bị mẹ mắng vì mải chơi trốn học, cậu vùng vằng tức giận bỏ nhà ra đi. Cậu lang thang khắp chốn cùng nơi, theo bạn bè rong chơi không biết bao nhiêu ngày tháng. Cậu không hề hay biết rằng ở nhà, người mẹ ngày đêm ngóng đợi, khóc cạn nước mắt vì thương nhớ con.

Đến khi trong túi không còn một xu dính túi, trời đông rét buốt cắt da cắt thịt, bụng đói lả và bị những đứa trẻ lớn hơn bắt nạt, cậu bé mới bùi ngùi nhớ đến mái ấm và sự chăm sóc dịu dàng của mẹ.

Cậu lần tìm đường về lại ngôi nhà xưa. Cảnh vật vẫn như trước, nhưng nhà cửa vắng lặng, bụi bám khắp nơi. Cậu cất tiếng gọi: "Mẹ ơi, con đã về rồi đây!", nhưng chỉ có tiếng gió xào xạc đáp lại. Người mẹ vì kiệt sức vì mong chờ đã ngã gục từ lâu.

Quá ân hận và xót xa, cậu bé ôm lấy một cái cây xanh tốt giữa vườn mà khóc nức nở. Kỳ lạ thay, thân cây bỗng run rẩy nhè nhẹ, từng cành lá rung rinh như bàn tay mẹ vỗ về.

Từ trên cao, những bông hoa trắng li ti bung nở thơm ngát, rồi hoa rụng, kết thành những quả tròn lẳn, bóng mịn. Cành cây trĩu quả nghiêng xuống sát tận tay cậu bé. Cậu háo hức đưa tay hái một quả rồi cắn vào, một dòng sữa trắng đục ngọt ngào và ấm áp như dòng sữa mẹ tuôn trào ra nuôi dưỡng cậu.

Cậu bé bật khóc nức nở trong nỗi ân hận muộn màng. Về sau, mọi người đem hạt cây ấy gieo trồng khắp nơi và đặt tên là cây Vú Sữa để nhắc nhở con cháu về tình mẫu tử thiêng liêng.`,
  },
  {
    id: 'tien-hiep-khai-phong',
    title: 'Tiên Hiệp: Con Đường Tu Tiên - Chương 1: Bắt Đầu Từ Vực Sâu',
    author: 'Huyền Huyễn',
    source: 'Tiểu thuyết tu chân kỳ ảo',
    content: `Trời chiều bảng lảng buông xuống vách núi Ma Lĩnh, mây mù cuồn cuộn tựa như biển sóng gầm gừ.

Trên một mỏm đá nhô ra giữa khoảng không hun hút, Diệp Phong chậm rãi thở hắt ra một ngụm khí trắng đục. Hắn siết chặt thanh trường kiếm rỉ sét trong tay, đôi mắt sáng rực ánh kiên định bất khuất.

Mười năm trước, gia tộc hắn bị diệt môn trong một đêm mưa tuyết gió rít. Mười năm nếm mật nằm gai, trải qua vô số hiểm nguy nơi sinh tử, hôm nay hắn rốt cuộc cũng bước chân vào Luyện Khí tầng thứ chín, chuẩn bị xung kích vào Trúc Cơ cảnh giới.

"Muốn nghịch thiên cải mệnh, thì trước hết phải dám đối diện với cái chết."

Diệp Phong thì thầm, sau đó khoanh chân ngồi xếp bằng trên phiến đá lạnh buốt. Từng luồng linh khí đất trời bắt đầu vần vũ hội tụ xung quanh kinh mạch hắn, tỏa ra ánh hào quang ngũ sắc lung linh huyền ảo giữa màn đêm cô tịch.

Bỗng nhiên, từ sâu trong rừng rậm bên dưới vang lên một tiếng gầm gừ trầm đục của hung thú cổ xưa, làm rung chuyển cả đất trời. Cơn bão táp số phận dường như chỉ mới bắt đầu bắt đầu...`,
  },
];
