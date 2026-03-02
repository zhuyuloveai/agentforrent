"""
端到端测试脚本
"""
import asyncio
import json
from src.agent.core import run
from src.tools.rent_api import init_houses


async def test_greeting():
    """测试1：问候（0次模型调用）"""
    print("=== 测试1: 问候 ===")
    result = await run("test001", "你好")
    print(f"Response: {result[:100]}")
    print()


async def test_simple_query():
    """测试2：单轮简单查询"""
    print("=== 测试2: 单轮简单查询 ===")
    await init_houses()
    result = await run("test002", "查询两居室房源")
    print(f"Response: {result[:300]}")

    # 尝试解析 JSON
    try:
        data = json.loads(result)
        print(f"Houses found: {len(data.get('houses', []))}")
    except:
        pass
    print()


async def test_complex_query():
    """测试3：单轮复杂查询"""
    print("=== 测试3: 单轮复杂查询 ===")
    await init_houses()
    result = await run("test003", "帮我找海淀区两居室，预算8000以内，要近地铁，精装修")
    print(f"Response: {result[:300]}")

    try:
        data = json.loads(result)
        print(f"Houses found: {len(data.get('houses', []))}")
    except:
        pass
    print()


async def test_multi_turn():
    """测试4：多轮对话"""
    print("=== 测试4: 多轮对话 ===")
    await init_houses()

    # 第一轮
    print("Round 1: 我想在朝阳区找房，预算10000以内")
    r1 = await run("test004", "我想在朝阳区找房，预算10000以内")
    print(f"Response 1: {r1[:200]}")

    # 第二轮
    print("\nRound 2: 要精装修的，而且要有电梯")
    r2 = await run("test004", "要精装修的，而且要有电梯")
    print(f"Response 2: {r2[:200]}")

    try:
        data = json.loads(r2)
        print(f"Houses found: {len(data.get('houses', []))}")
    except:
        pass
    print()


async def test_rent_operation():
    """测试5：租房操作"""
    print("=== 测试5: 租房操作 ===")
    await init_houses()

    # 先查房
    r1 = await run("test005", "查询海淀区的房源")
    print(f"Query result: {r1[:200]}")

    # 提取第一个房源ID
    try:
        data = json.loads(r1)
        houses = data.get('houses', [])
        if houses:
            house_id = houses[0]
            print(f"\nTrying to rent: {house_id}")
            r2 = await run("test005", f"我想租{house_id}这套")
            print(f"Rent result: {r2[:200]}")
    except Exception as e:
        print(f"Error: {e}")
    print()


async def main():
    print("=" * 60)
    print("租房 AI Agent 端到端测试")
    print("=" * 60)
    print()

    try:
        await test_greeting()
        await test_simple_query()
        await test_complex_query()
        await test_multi_turn()
        await test_rent_operation()

        print("=" * 60)
        print("测试完成！")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
